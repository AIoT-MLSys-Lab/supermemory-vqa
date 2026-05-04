"""
Shared service instances for visualization routes.
"""
from annotation.service import VideoAnnotationService

# Default service instance for loading/saving annotations
annotation_service = VideoAnnotationService()


def build_annotation_service(model_name: str) -> VideoAnnotationService:
    """Factory to create a service with a specific model."""
    return VideoAnnotationService(model_name=model_name)
