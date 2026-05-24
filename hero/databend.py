#!/usr/bin/env python3
"""
vdcrpt-style databender for h264 Annex B streams.

Pipeline (run via make_hero.sh):
  mp4 -> Annex B h264 elementary stream -> corrupt NALs -> mp4

The "splice & replace" trick: copy a random chunk of bytes from somewhere
in the stream over another random location, so motion-vector predictions
reference the wrong data. With sparse keyframes the wrongness propagates
across many frames -- the signature datamosh smear.
"""
import argparse, os, random, sys

NAL_SC = b"\x00\x00\x00\x01"  # 4-byte start code (Annex B)
NAL_SC3 = b"\x00\x00\x01"     # 3-byte start code (also legal)


def find_nals(buf: bytes):
    """Yield (start_offset, header_byte_offset) for each NAL unit."""
    i = 0
    n = len(buf)
    while i < n - 4:
        if buf[i:i+4] == NAL_SC:
            yield i, i + 4
            i += 4
        elif buf[i:i+3] == NAL_SC3:
            yield i, i + 3
            i += 3
        else:
            i += 1


def nal_type(buf, header_off):
    return buf[header_off] & 0x1F


# h264 NAL types we want to leave alone -- anything that the decoder
# uses to set up state. Slices = 1, 5 (IDR). We corrupt 1 (P/B-slice
# non-IDR) freely; we leave 5 (IDR) alone so each clip still has a
# clean anchor frame. SPS=7, PPS=8, SEI=6 -- never touch.
SAFE_TYPES = {5, 6, 7, 8, 9, 10, 11, 12}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--ops", type=int, default=40,
                    help="number of splice operations")
    ap.add_argument("--max-chunk", type=int, default=4096,
                    help="max bytes per splice")
    ap.add_argument("--min-chunk", type=int, default=64)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    with open(args.input, "rb") as f:
        buf = bytearray(f.read())

    # Build a list of corruptible byte ranges (inside non-IDR slices).
    nal_offsets = list(find_nals(bytes(buf)))
    nal_offsets.append((len(buf), len(buf)))  # sentinel for end

    corruptible = []  # list of (start, end) byte ranges, payload only
    for (start, header_off), (next_start, _) in zip(nal_offsets, nal_offsets[1:]):
        t = nal_type(buf, header_off)
        # payload begins right after the 1-byte NAL header
        payload_start = header_off + 1
        payload_end = next_start
        if t in SAFE_TYPES:
            continue
        if payload_end - payload_start < args.min_chunk * 2:
            continue
        corruptible.append((payload_start, payload_end))

    if not corruptible:
        print("no corruptible ranges found", file=sys.stderr)
        sys.exit(1)

    print(f"found {len(corruptible)} corruptible NAL slices "
          f"({sum(e-s for s,e in corruptible):,} bytes)", file=sys.stderr)

    # Apply N splice ops
    for _ in range(args.ops):
        src_range = random.choice(corruptible)
        dst_range = random.choice(corruptible)
        chunk_size = random.randint(args.min_chunk, args.max_chunk)
        # clamp
        chunk_size = min(chunk_size,
                         src_range[1] - src_range[0],
                         dst_range[1] - dst_range[0])
        if chunk_size < args.min_chunk:
            continue
        src_off = random.randint(src_range[0], src_range[1] - chunk_size)
        dst_off = random.randint(dst_range[0], dst_range[1] - chunk_size)
        # avoid emergent 00 00 00 01 sequences in the replacement (would
        # confuse downstream demuxers). Cheap heuristic: skip if the
        # source chunk contains a start code.
        chunk = bytes(buf[src_off:src_off + chunk_size])
        if NAL_SC in chunk or NAL_SC3 in chunk:
            continue
        buf[dst_off:dst_off + chunk_size] = chunk

    with open(args.output, "wb") as f:
        f.write(buf)
    print(f"wrote {args.output} ({len(buf):,} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
