import openl3
import soundfile as sf
import numpy as np
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# OpenL3 expects audio to be at 48kHz. 
# The get_audio_embedding function handles resampling if needed, but it's good to be aware.
TARGET_SR = 48000 

def get_openl3_embedding(
    audio_file_path: str, 
    input_repr: str = "mel256", 
    content_type: str = "music", 
    embedding_size: int = 512
) -> Optional[np.ndarray]:
    """
    Generates an OpenL3 embedding for the given audio file.

    Args:
        audio_file_path: Path to the audio file.
        input_repr: OpenL3 input representation ('linear', 'mel128', 'mel256').
        content_type: OpenL3 content type ('music', 'env').
        embedding_size: OpenL3 embedding size (512 or 6144).

    Returns:
        A NumPy array representing the mean embedding for the audio file, 
        or None if an error occurs.
    """
    try:
        audio, sr = sf.read(audio_file_path)
        if audio is None:
            logger.error(f"Could not read audio from {audio_file_path}")
            return None

        logger.info(f"Successfully read audio from {audio_file_path}, SR: {sr}, Shape: {audio.shape}")

        # Get embedding. This function can handle mono or stereo audio.
        # It returns a list of embedding vectors (emb_list) and a list of corresponding timestamps (ts_list).
        # For a short clip (e.g., 20s), we might get multiple embeddings if OpenL3's hop size is small.
        # We will average these embeddings to get a single representative vector for the clip.
        emb_list, ts_list = openl3.get_audio_embedding(
            audio, 
            sr, 
            input_repr=input_repr, 
            content_type=content_type, 
            embedding_size=embedding_size
        )

        if emb_list is None or len(emb_list) == 0:
            logger.error(f"OpenL3 did not return any embeddings for {audio_file_path}.")
            return None

        # Average the embeddings to get a single vector representation for the clip
        mean_embedding = np.mean(emb_list, axis=0)
        logger.info(f"Generated OpenL3 embedding for {audio_file_path}. Shape: {mean_embedding.shape}")
        
        return mean_embedding

    except Exception as e:
        logger.error(f"Error generating OpenL3 embedding for {audio_file_path}: {e}", exc_info=True)
        return None

if __name__ == '__main__':
    # Create a dummy audio file for testing (e.g., a 20-second sine wave)
    # This requires numpy and soundfile to be installed.
    import os
    dummy_audio_dir = "temp_audio_test_openl3"
    os.makedirs(dummy_audio_dir, exist_ok=True)
    dummy_file_path = os.path.join(dummy_audio_dir, "dummy_sine_20s.wav")
    
    sr_test = 44100  # A common sample rate
    duration_test = 20  # seconds
    frequency_test = 440  # Hz (A4 note)
    t_test = np.linspace(0, duration_test, int(sr_test * duration_test), False)
    audio_data_test = 0.5 * np.sin(2 * np.pi * frequency_test * t_test)
    
    # Ensure audio_data_test is 1D for sf.write with mono
    if audio_data_test.ndim > 1:
        audio_data_test = np.mean(audio_data_test, axis=1) # Example: average if stereo

    try:
        sf.write(dummy_file_path, audio_data_test, sr_test)
        print(f"Created dummy audio file: {dummy_file_path}")

        print(f"\nAttempting to generate OpenL3 embedding for {dummy_file_path}...")
        # Test with default music model (mel256, 512 dim)
        embedding_music_512 = get_openl3_embedding(dummy_file_path, input_repr="mel256", content_type="music", embedding_size=512)
        if embedding_music_512 is not None:
            print(f"Music model (mel256, 512) embedding shape: {embedding_music_512.shape}")
            # print(embedding_music_512[:10]) # Print first 10 values
        else:
            print("Failed to get music model (mel256, 512) embedding.")

        # Test with default music model (mel256, 6144 dim) - larger embedding
        # embedding_music_6144 = get_openl_embedding(dummy_file_path, input_repr="mel256", content_type="music", embedding_size=6144)
        # if embedding_music_6144 is not None:
        #     print(f"Music model (mel256, 6144) embedding shape: {embedding_music_6144.shape}")
        # else:
        #     print("Failed to get music model (mel256, 6144) embedding.")

        # Test with environmental sound model (linear, 6144 dim)
        # embedding_env_6144 = get_openl_embedding(dummy_file_path, input_repr="linear", content_type="env", embedding_size=6144)
        # if embedding_env_6144 is not None:
        #    print(f"Environmental model (linear, 6144) embedding shape: {embedding_env_6144.shape}")
        # else:
        #    print("Failed to get environmental model (linear, 6144) embedding.")

    except Exception as e_main:
        print(f"An error occurred in the main test block: {e_main}")
    finally:
        # Clean up dummy file
        if os.path.exists(dummy_file_path):
            try:
                os.remove(dummy_file_path)
                os.rmdir(dummy_audio_dir) # Remove dir if empty
                print(f"Cleaned up dummy audio file and directory: {dummy_file_path}")
            except Exception as e_clean:
                print(f"Error cleaning up dummy file/dir: {e_clean}") 