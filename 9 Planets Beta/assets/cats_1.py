import sys
import time
import cv2

def play_hyper_accelerated_mp4(video_path, speed_multiplier=4):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Native engine could not read video file at {video_path}")
        return

    # Decode only the first frame before creating the window. This prevents a
    # blank surface without making the player wait for the whole clip.
    ret, first_frame = cap.read()
    if not ret:
        cap.release()
        print(f"Error: No frames could be read from {video_path}")
        return

    print(f"Streaming Hyper-Accelerated ({speed_multiplier}x target): {video_path}")
    print("Press 'q' or 'ESC' to stop playback.")

    window_name = "Hyper-Accelerated Playback Engine"
    
    # Setup window and force full screen
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    try:
        cv2.imshow(window_name, first_frame)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_delay_ms = max(1, int(1000 / (fps * speed_multiplier)))
        cv2.waitKey(frame_delay_ms)
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(frame_delay_ms) & 0xFF
            if key == ord('q') or key == 27:  # 'q' or ESC
                print("\nPlayback terminated by user.")
                break

    except KeyboardInterrupt:
        print("\nProcess interrupted via console.")
    finally:
        time.sleep(0.10)
        cap.release()
        cv2.destroyAllWindows()
        print("Engine closed cleanly.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py cats_1.py <path_to_video.mp4>")
    else:
        play_hyper_accelerated_mp4(sys.argv[1], speed_multiplier=4)
