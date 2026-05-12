
import asyncio
from app.orchestrator import run_complaint_pipeline
from app.schemas.issue_schema import MediaMetadata, MediaType
from datetime import datetime, timezone

async def test():
    media = MediaMetadata(
        media_url="https://example.com/video.mp4",
        media_type=MediaType.VIDEO,
        platform="app",
        posted_at=datetime.now(timezone.utc),
        geotag="Rohini, Delhi",
        caption="Pothole on the road",
        reporter_handle="test-user"
    )
    
    print("Starting pipeline...")
    try:
        # If run_complaint_pipeline is sync, this should work
        complaint = run_complaint_pipeline(media)
        print(f"Status: {complaint.status}")
        print(f"Authority: {complaint.authority_name}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
