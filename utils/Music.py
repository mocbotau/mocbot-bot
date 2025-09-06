from datetime import datetime
import re
import shortuuid


def format_duration(ms: int) -> str:
    """Format duration from milliseconds to a human-readable string."""
    return datetime.fromtimestamp(ms / 1000).strftime("%Hh %Mm %Ss")


def convert_to_ms(time: str) -> int | None:
    """Convert a time string in HH:MM:SS format to total milliseconds. Returns None if time is
    None, or -1 if format is invalid."""
    if time is None:
        return None
    if re.match(r"^(?:(?:([01]?\d|2[0-3]):)?([0-5]?\d):)?([0-5]?\d)$", time):
        return sum(int(x) * 60**i for i, x in enumerate(reversed(time.split(":")))) * 1000

    return -1


def is_youtube_url(url: str) -> re.Match | None:
    """Check if a URL is a valid YouTube URL."""
    return re.match(
        r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(-nocookie)?\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)"
        r"([\w\-]+)(\S+)?$",
        url,
    )


def queue_length_msg(length: int) -> str:
    """Generate a message indicating the number of tracks in the queue."""
    return f"There {'is' if length == 1 else 'are'} **{length}** " f"track{'' if length == 1 else 's'} in the queue."


def format_lyrics_for_display(lyrics: str, max_length: int = 2000) -> list[str]:
    """Split lyrics into displayable chunks that each fit within max_length."""
    if not lyrics:
        return ["No lyrics available"]

    chunks: list[str] = []
    remaining_text = lyrics.strip()

    while remaining_text:
        if len(remaining_text) <= max_length:
            chunks.append(remaining_text)
            break

        # Find best split point before max_length
        split_point = remaining_text.rfind("\n", 0, max_length)
        if split_point == -1:
            split_point = remaining_text.rfind(" ", 0, max_length)
            if split_point == -1:
                split_point = max_length  # force split if no good boundary

        chunk = remaining_text[:split_point].rstrip()
        chunks.append(chunk)
        remaining_text = remaining_text[split_point:].lstrip()

    return chunks


def create_id() -> str:
    """Create a short unique ID."""
    return shortuuid.uuid()[:6].lower()
