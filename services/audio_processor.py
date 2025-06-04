import logging
from typing import Optional, List
import numpy as np

from .audio_embedding_service import get_openl3_embedding, TARGET_SR # Assuming OpenL3 specific settings might be relevant here

logger = logging.getLogger(__name__)

def process_audio_segment(audio_file_path: str) -> Optional[List[float]]:
    """
    Processes an audio segment file to extract an embedding.

    Args:
        audio_file_path: The path to the audio segment file.

    Returns:
        A list of floats representing the audio embedding, or None if processing fails.
    """
    logger.info(f"Processing audio segment: {audio_file_path}")
    try:
        # Using default parameters for OpenL3 for now, consistent with audio_embedding_service
        embedding_np_array = get_openl3_embedding(
            audio_file_path=audio_file_path,
            input_repr="mel256", # Default from audio_embedding_service
            content_type="music", # Default from audio_embedding_service
            embedding_size=512    # Default from audio_embedding_service
        )

        if embedding_np_array is not None:
            # Convert NumPy array to a list of floats for easier serialization/storage
            embedding_list = embedding_np_array.tolist()
            logger.info(f"Successfully generated embedding for {audio_file_path}. Embedding dimension: {len(embedding_list)}")
            return embedding_list
        else:
            logger.warning(f"Failed to generate embedding for {audio_file_path}. get_openl3_embedding returned None.")
            return None

    except Exception as e:
        logger.error(f"Error processing audio segment {audio_file_path}: {e}", exc_info=True)
        return None

if __name__ == '__main__':
    # This section allows for standalone testing of audio_processor.py
    # It requires a sample audio file. We can reuse the dummy file creation logic
    # from audio_embedding_service.py for a self-contained test.

    import os
    import soundfile as sf # Required for creating the dummy file

    dummy_audio_dir = "temp_audio_test_processor"
    os.makedirs(dummy_audio_dir, exist_ok=True)
    dummy_file_path_processor = os.path.join(dummy_audio_dir, "dummy_sine_5s_processor.wav")
    
    sr_test = TARGET_SR # Use the target SR for OpenL3
    duration_test = 5  # seconds, shorter for a quick test
    frequency_test = 440  # Hz (A4 note)
    t_test = np.linspace(0, duration_test, int(sr_test * duration_test), False)
    audio_data_test = 0.5 * np.sin(2 * np.pi * frequency_test * t_test)
    
    if audio_data_test.ndim > 1:
        audio_data_test = np.mean(audio_data_test, axis=1)

    try:
        sf.write(dummy_file_path_processor, audio_data_test, sr_test)
        print(f"Created dummy audio file for testing: {dummy_file_path_processor}")

        print(f"Attempting to process audio segment: {dummy_file_path_processor}...")
        embedding = process_audio_segment(dummy_file_path_processor)

        if embedding:
            print(f"Successfully processed segment. Embedding (first 10 values): {embedding[:10]}")
            print(f"Full embedding dimension: {len(embedding)}")
        else:
            print(f"Failed to process segment: {dummy_file_path_processor}")

    except Exception as e_main:
        print(f"An error occurred in the main test block of audio_processor.py: {e_main}")
    finally:
        if os.path.exists(dummy_file_path_processor):
            try:
                os.remove(dummy_file_path_processor)
                # Attempt to remove the directory if it's empty
                if not os.listdir(dummy_audio_dir):
                    os.rmdir(dummy_audio_dir)
                print(f"Cleaned up dummy audio file and directory: {dummy_file_path_processor}")
            except Exception as e_clean:
                print(f"Error cleaning up: {e_clean}") 