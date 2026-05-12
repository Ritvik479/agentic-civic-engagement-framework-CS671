
import asyncio
import os
from app.orchestrator import run_complaint_pipeline
from app.schemas.issue_schema import MediaMetadata, MediaType
from datetime import datetime, timezone

async def test():
    video_path = os.path.abspath("data/test_vision/videos/garbage_dump.mp4")
    media = MediaMetadata(
        media_url=f"file://{video_path}",
        media_type=MediaType.VIDEO,
        platform="app",
        posted_at=datetime.now(timezone.utc),
        geotag="Kalyan, Maharashtra",
        caption="Garbage dump near my house",
        reporter_handle="test-user"
    )
    
    print(f"Starting pipeline for: {video_path}")
    complaint = run_complaint_pipeline(media)
    print(f"Status: {complaint.status}")
    print(f"Authority: {complaint.authority_name}")
    print(f"Description: {complaint.issue_description}")
    print(f"Errors: {complaint.validation_errors}")

if __name__ == "__main__":
    asyncio.run(test())
