import re

INPUT_FILE = "sample_auto.vtt"
OUTPUT_FILE = "sample_clean.srt"


def is_timestamp(line):
    return "-->" in line


def is_metadata(line):
    return (
        line.strip() == "" or
        line.startswith("WEBVTT") or
        line.startswith("Kind:") or
        line.startswith("Language:")
    )


def clean_vtt_lines(lines):
    cleaned = []
    prev_line = None

    for line in lines:
        line = line.strip()

        # skip timestamps and metadata
        if is_timestamp(line) or is_metadata(line):
            continue

        # remove HTML tags (very common in YouTube VTT)
        line = re.sub(r"<.*?>", "", line)

        # remove duplicate consecutive lines
        if line == prev_line:
            continue

        if line:
            cleaned.append(line)
            prev_line = line

    return cleaned


def write_srt(lines):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    cleaned_lines = clean_vtt_lines(lines)
    write_srt(cleaned_lines)

    print(f"✅ Cleaned subtitles saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()