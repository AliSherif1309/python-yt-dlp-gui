import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import yt_dlp
import threading
import os
import re
import traceback
from typing import List, Dict, Any, Optional # For type hinting

# --- Constants ---
VIDEO_TYPE = "video"
AUDIO_TYPE = "audio"
DEFAULT_AUDIO_CODEC = "mp3" # Or 'm4a', 'opus', etc.
DEFAULT_AUDIO_QUALITY = "192" # kbit/s

class YouTubeDownloaderApp:
    """
    A Tkinter GUI application for downloading multiple YouTube videos or audio
    using yt-dlp, with optional playlist handling and container choice.
    """
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("YouTube Multi-Downloader (yt-dlp)")
        self.root.geometry("600x550") # Adjusted height

        # --- Style ---
        self.style = ttk.Style()
        self.style.theme_use('clam') # Or 'alt', 'default', 'classic'

        # --- Variables ---
        self.download_type_var = tk.StringVar(value=VIDEO_TYPE)
        self.download_path_var = tk.StringVar(value=os.getcwd())
        self.status_var = tk.StringVar(value="Status: Idle")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.overall_progress_var = tk.StringVar(value="") # For X/Y progress
        self.download_playlists_var = tk.BooleanVar(value=False)
        self.container_format_var = tk.StringVar(value="mp4") # Default to mp4
        # --- Internal State ---
        self.is_downloading = False
        self.download_thread: Optional[threading.Thread] = None
        self.cancelled = False # Flag for explicit cancellation

        # --- GUI Elements ---
        self.setup_gui()

        # --- Window Closing Protocol ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_gui(self):
        """Creates and grids all the GUI elements."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        # --- URL Input ---
        ttk.Label(main_frame, text="YouTube URLs (One per line):").grid(row=0, column=0, padx=5, pady=5, sticky="nw")
        self.url_text = scrolledtext.ScrolledText(main_frame, height=8, width=60, wrap=tk.WORD)
        self.url_text.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

        # --- Download Options ---
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="10")
        options_frame.grid(row=2, column=0, columnspan=3, padx=5, pady=10, sticky="ew")

        # --- Create Widgets FIRST (Order matters for dependencies later) ---

        # Download Type Widgets
        self.video_radio = ttk.Radiobutton(options_frame, text="Video", variable=self.download_type_var, value=VIDEO_TYPE)
        self.audio_radio = ttk.Radiobutton(options_frame, text=f"Audio Only ({DEFAULT_AUDIO_CODEC.upper()})*", variable=self.download_type_var, value=AUDIO_TYPE)

        # Video Container Widgets
        self.container_label = ttk.Label(options_frame, text="Video Container:")
        self.container_frame = ttk.Frame(options_frame) # Frame to hold the radio buttons horizontally
        self.mp4_radio = ttk.Radiobutton(self.container_frame, text="MP4", variable=self.container_format_var, value="mp4")
        self.mkv_radio = ttk.Radiobutton(self.container_frame, text="MKV*", variable=self.container_format_var, value="mkv")

        # Save Location Widgets
        self.path_entry = ttk.Entry(options_frame, textvariable=self.download_path_var, width=40, state='readonly')
        self.browse_button = ttk.Button(options_frame, text="Browse...", command=self.browse_directory)

        # Playlist Widget
        self.playlist_checkbox = ttk.Checkbutton(options_frame, text="Download Playlists (creates subfolder)", variable=self.download_playlists_var)

        # FFmpeg Note Widget
        self.ffmpeg_note = ttk.Label(options_frame, text=f"*Audio ({DEFAULT_AUDIO_CODEC.upper()}) or MKV selection requires FFmpeg in PATH. Playlists create subfolders.", font=('Helvetica', 8), foreground='gray')


        # --- Grid Widgets in Order ---

        # Row 0: Download Type
        ttk.Label(options_frame, text="Download Type:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.video_radio.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.audio_radio.grid(row=0, column=2, padx=5, pady=5, sticky="w")

        # Row 1: Video Container
        self.container_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.container_frame.grid(row=1, column=1, columnspan=2, padx=0, pady=0, sticky="w")
        # Use pack for items inside the container_frame
        self.mp4_radio.pack(side=tk.LEFT, padx=5)
        self.mkv_radio.pack(side=tk.LEFT, padx=5)

        # Row 2: Save Location
        ttk.Label(options_frame, text="Save Location:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.path_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.browse_button.grid(row=2, column=2, padx=5, pady=5, sticky="ew")

        # Row 3: Playlist Checkbox
        self.playlist_checkbox.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="w")

        # Row 4: FFmpeg Note
        self.ffmpeg_note.grid(row=4, column=0, columnspan=3, padx=5, pady=(0, 5), sticky="w")


        # --- Finish Options Frame Setup ---
        options_frame.columnconfigure(1, weight=1) # Make entry expand

        # Add callback to enable/disable container options
        self.download_type_var.trace_add("write", self._toggle_container_options)
        # Initial call to set the correct state right after creation
        self._toggle_container_options()
        # ---

        # --- Action Button ---
        self.download_button = ttk.Button(main_frame, text="Download All Entered URLs", command=self.start_download_thread)
        self.download_button.grid(row=3, column=0, columnspan=3, padx=5, pady=10, sticky="ew") # Row adjusted

        # --- Progress & Status ---
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky="ew") # Row adjusted

        ttk.Label(progress_frame, text="Current File:").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, length=400)
        self.progress_bar.grid(row=0, column=1, padx=5, pady=2, sticky="ew")

        ttk.Label(progress_frame, text="Overall:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.overall_progress_label = ttk.Label(progress_frame, textvariable=self.overall_progress_var)
        self.overall_progress_label.grid(row=1, column=1, padx=5, pady=2, sticky="w")

        progress_frame.columnconfigure(1, weight=1) # Make progress bar expand

        self.status_label = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w", wraplength=550)
        self.status_label.grid(row=5, column=0, columnspan=3, padx=5, pady=(10, 5), sticky="ew") # Row adjusted

        # --- Configure main_frame grid ---
        main_frame.columnconfigure(1, weight=1) # Text/Entry column expands
        main_frame.rowconfigure(1, weight=1) # Make Text widget expand vertically


    def _toggle_container_options(self, *args):
        """Enables/disables the container format radio buttons based on download type."""
        if self.download_type_var.get() == VIDEO_TYPE:
            state = tk.NORMAL
            self.container_label.configure(state=tk.NORMAL) # Enable label too
        else:
            state = tk.DISABLED
            self.container_label.configure(state=tk.DISABLED) # Disable label

        self.mp4_radio.configure(state=state)
        self.mkv_radio.configure(state=state)


    def browse_directory(self):
        """Opens a dialog to choose a download directory."""
        if self.is_downloading: return
        path = filedialog.askdirectory(initialdir=self.download_path_var.get())
        if path:
            self.download_path_var.set(path)

    def update_status(self, message: str):
        """Thread-safe way to update the status bar."""
        self.root.after(0, lambda msg=message: self.status_var.set(f"Status: {msg}"))

    def update_progress(self, percentage: float, status_message: str = ""):
        """Thread-safe way to update the progress bar and optionally the status."""
        self.root.after(0, lambda p=percentage: self.progress_var.set(p))
        if status_message:
             self.update_status(status_message)

    def update_overall_progress(self, current: int, total: int):
        """Thread-safe way to update the overall progress label."""
        msg = f"{current}/{total}"
        self.root.after(0, lambda m=msg: self.overall_progress_var.set(m))

    def set_ui_state(self, enabled: bool):
        """Enable or disable UI elements during download."""
        # Determine state based on 'enabled' flag AND specific conditions
        base_state = tk.NORMAL if enabled else tk.DISABLED
        container_state = tk.NORMAL if enabled and self.download_type_var.get() == VIDEO_TYPE else tk.DISABLED

        # Widgets always enabled/disabled with base_state
        base_widgets = [
            self.url_text, self.browse_button, self.download_button,
            self.video_radio, self.audio_radio,
            self.playlist_checkbox
        ]
        for widget in base_widgets:
            # ScrolledText needs special handling for state
            if isinstance(widget, scrolledtext.ScrolledText):
                 widget.configure(state=base_state)
            else:
                widget.configure(state=base_state)

        # Container widgets depend on download type as well
        self.container_label.configure(state=container_state)
        self.mp4_radio.configure(state=container_state)
        self.mkv_radio.configure(state=container_state)


    def reset_ui_after_download(self):
        """Resets the UI elements to their initial state after download finishes or fails."""
        self.is_downloading = False
        self.cancelled = False # Reset cancellation flag
        self.root.after(0, lambda: self.set_ui_state(True))
        self.root.after(0, lambda: self.progress_var.set(0.0))
        self.root.after(0, lambda: self.overall_progress_var.set("")) # Clear overall progress


    def my_yt_dlp_progress_hook(self, d: Dict[str, Any]):
        """Hook for yt-dlp to update progress, checking for cancellation."""
        if self.cancelled:
             # Must raise an exception yt-dlp understands to truly stop it
             raise yt_dlp.utils.DownloadCancelled('Download cancelled by user.')

        status = d.get('status')
        filename = os.path.basename(d.get('filename', ''))
        info_dict = d.get('info_dict', {}) # Extract info_dict if available
        # Try to get playlist info for status
        playlist_title = info_dict.get('playlist_title', info_dict.get('playlist'))
        playlist_index = info_dict.get('playlist_index')
        # Get title from info_dict preferably, fallback to filename
        title = info_dict.get('title', os.path.splitext(filename)[0] if filename else 'Unknown Title')

        # Construct prefix for status messages if part of a playlist download
        status_prefix = ""
        if playlist_title and playlist_index is not None:
             status_prefix = f"Playlist '{playlist_title}' ({playlist_index}/{info_dict.get('n_entries', '?')}): "


        if status == 'downloading':
            total_bytes_estimate = d.get('total_bytes_estimate')
            total_bytes = d.get('total_bytes', total_bytes_estimate)
            downloaded_bytes = d.get('downloaded_bytes')

            if total_bytes and downloaded_bytes:
                percentage = (downloaded_bytes / total_bytes) * 100
                speed = d.get('speed')
                eta = d.get('eta')
                speed_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed else "..."
                eta_str = f"{eta}s" if eta is not None else "..." # Handle None eta
                status_msg = f"Downloading: {status_prefix}{title} | {percentage:.1f}% ({speed_str}, ETA: {eta_str})"
                self.update_progress(percentage, status_msg)
            else:
                 # Sometimes only filename is available initially
                 status_msg = f"Downloading: {status_prefix}{title} (Waiting for size info...)"
                 self.update_status(status_msg)
                 self.root.after(0, lambda: self.progress_var.set(0)) # Reset bar if no size info

        elif status == 'finished':
            # Get final filename from info_dict if possible (often includes path)
            final_filename = os.path.basename(info_dict.get('filepath', filename))
            if not final_filename: # Fallback if filepath isn't in info_dict yet
                 final_filename = filename if filename else title

            self.update_status(f"Finished: {status_prefix}{final_filename}")
            # Reset progress bar visually for the next file in the loop (or completion)
            # Small delay helps visually separate finishes
            self.root.after(100, lambda: self.progress_var.set(0))

        elif status == 'error':
             # Include prefix if available, otherwise just title
             display_name = f"{status_prefix}{title}" if status_prefix else title
             self.update_status(f"Error downloading: {display_name}")
             # Error details will be caught in the main download loop


    def download_content(self, urls_to_download: List[str], download_path: str, download_type: str, should_download_playlists: bool, container_format: Optional[str]):
        """
        Handles the download logic using yt-dlp.

        Args:
            urls_to_download: List of URL strings.
            download_path: The base directory path to save files.
            download_type: Either VIDEO_TYPE or AUDIO_TYPE.
            should_download_playlists: Boolean indicating if playlists should be downloaded.
            container_format: 'mp4' or 'mkv' if download_type is VIDEO_TYPE, else None.
        """
        self.is_downloading = True
        self.cancelled = False
        total_urls = len(urls_to_download)
        failed_items: List[Dict[str, str]] = [] # Store URL-level failures

        # --- Base yt-dlp Options ---
        base_ydl_opts: Dict[str, Any] = {
            'progress_hooks': [self.my_yt_dlp_progress_hook],
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'noplaylist': not should_download_playlists,
            'quiet': True,
            'verbose': False,
            'no_warnings': True,
            'updatetime': False,
            'postprocessors': [], # Initialize postprocessors list
            'format': None, # Define later
            'merge_output_format': None, # Define later
        }

        # --- Set Output Template ---
        if should_download_playlists:
             base_ydl_opts['outtmpl'] = os.path.join(
                 download_path,
                 '%(playlist)s',
                 '%(playlist_index)02d - %(title)s [%(id)s].%(ext)s'
             )
        else:
            base_ydl_opts['outtmpl'] = os.path.join(
                download_path,
                '%(title)s [%(id)s].%(ext)s'
            )

        # --- Set Format, Merge Format, and Postprocessors ---
        if download_type == VIDEO_TYPE:
            # Select best formats, preferring widely compatible ones first
            base_ydl_opts['format'] = 'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc]+bestaudio/bestvideo+bestaudio/best[ext=mp4]/best'

            # Set merge format based on user selection
            if container_format == 'mkv':
                base_ydl_opts['merge_output_format'] = 'mkv'
                # NOTE: Relying on merge_output_format primarily. Omitting explicit remuxer PP for now.
            else: # Default to mp4
                base_ydl_opts['merge_output_format'] = 'mp4'

        elif download_type == AUDIO_TYPE:
            base_ydl_opts['format'] = 'bestaudio/best'
            base_ydl_opts['postprocessors'].append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': DEFAULT_AUDIO_CODEC,
                'preferredquality': DEFAULT_AUDIO_QUALITY,
            })

        # Remove unset/empty keys
        if base_ydl_opts['format'] is None: del base_ydl_opts['format']
        if base_ydl_opts['merge_output_format'] is None: del base_ydl_opts['merge_output_format']
        if not base_ydl_opts.get('postprocessors'): # Use .get() for safety
             if 'postprocessors' in base_ydl_opts:
                 del base_ydl_opts['postprocessors']

        # --- Create yt-dlp instance ---
        try:
            # Uncomment to print final options for debugging
            # print("--- Effective yt-dlp options ---")
            # import json
            # print(json.dumps(base_ydl_opts, indent=2))
            # print("-----------------------------")
            ydl = yt_dlp.YoutubeDL(base_ydl_opts)
        except Exception as e:
             self.update_status(f"Error initializing yt-dlp: {e}")
             print(f"yt-dlp Initialization Error:\n{traceback.format_exc()}")
             self.reset_ui_after_download()
             messagebox.showerror("Initialization Error", f"Failed to initialize yt-dlp. Check options/installation.\nError: {e}")
             return

        # --- Loop Through Each Input URL ---
        loop_start_index = 0
        for i, current_url in enumerate(urls_to_download):
            loop_start_index = i
            if self.cancelled:
                self.update_status("Download cancelled by user.")
                break

            self.update_overall_progress(i + 1, total_urls)
            self.update_status(f"Processing input URL {i+1}/{total_urls}: {current_url}")
            self.root.after(0, lambda: self.progress_var.set(0.0))

            try:
                # Execute download for the URL (single or playlist)
                ydl.download([current_url])

            except yt_dlp.utils.DownloadCancelled:
                 self.update_status("Download cancelled during operation.")
                 break

            except (yt_dlp.utils.ExtractorError, yt_dlp.utils.DownloadError) as e:
                 error_message = f"Error processing URL ({i+1}): {current_url} - {type(e).__name__}: {e}"
                 self.update_status(error_message)
                 print(f"ERROR processing URL: {current_url}\n{traceback.format_exc()}")
                 failed_items.append({'item': current_url, 'error': str(e)})

            except Exception as e:
                error_message = f"Unexpected Error ({i+1}): {current_url} - {type(e).__name__}: {e}"
                self.update_status(error_message)
                print(f"UNEXPECTED ERROR processing URL: {current_url}\n{traceback.format_exc()}")
                failed_items.append({'item': current_url, 'error': f"Unexpected: {e}"})

        # --- End of Loop ---
        self.reset_ui_after_download()

        # --- Final Summary Message ---
        processed_url_count = loop_start_index + 1 if not self.cancelled else loop_start_index
        if self.cancelled and processed_url_count == 0 and total_urls > 0: processed_url_count=1 # Handle cancel before first URL
        final_status = f"Finished processing {processed_url_count} of {total_urls} input URLs."

        if self.cancelled:
            messagebox.showwarning("Cancelled", final_status)
        elif not failed_items:
            messagebox.showinfo("Finished", f"{final_status}\nCheck download folder(s). Status log may show individual item errors.")
        else:
            fail_count = len(failed_items)
            final_message = f"{final_status}\n\n" \
                            f"{fail_count} input URL(s) encountered significant errors (check console log):\n"
            for fail in failed_items[:5]:
                final_message += f"- {fail['item']} ({fail['error']})\n"
            if fail_count > 5:
                final_message += "- ... (See console for full list)\n"
            final_message += "\nNote: With 'ignoreerrors', individual items within playlists might fail without being listed here. Check status log during download."
            messagebox.showwarning("Finished with Errors", final_message)


    def start_download_thread(self):
        """Validates input and starts the download process in a separate thread."""
        if self.is_downloading:
            messagebox.showwarning("Busy", "A download is already in progress.")
            return

        # Read URLs from Text widget
        urls_text = self.url_text.get("1.0", tk.END)
        raw_urls = urls_text.splitlines()
        urls_to_download = [url.strip() for url in raw_urls if url.strip()]

        download_path = self.download_path_var.get()
        download_type = self.download_type_var.get()
        should_download_playlists = self.download_playlists_var.get()
        # Get container preference (only relevant if video type selected)
        container_format = self.container_format_var.get() if download_type == VIDEO_TYPE else None

        # --- Input Validation ---
        if not urls_to_download:
            messagebox.showerror("Input Error", "Please enter at least one YouTube URL.")
            return
        if not download_path:
            messagebox.showerror("Input Error", "Please select a download location.")
            return
        if not os.path.isdir(download_path):
            messagebox.showerror("Path Error", f"The selected download path is not a valid directory:\n{download_path}")
            return
        try: # Test write permissions
             test_file = os.path.join(download_path, ".permission_test")
             with open(test_file, "w") as f: f.write("test")
             os.remove(test_file)
        except Exception as e:
             messagebox.showerror("Path Error", f"Cannot write to the selected download path:\n{download_path}\nError: {e}")
             return

        # --- Basic URL Format Check (Optional) ---
        valid_urls = []
        invalid_lines = []
        youtube_pattern = re.compile(
             r"^(https?://)?(www\.)?(youtube\.com/|youtu\.be/)"
             r"(watch\?v=|playlist\?list=|shorts/|embed/|c/|channel/|user/|@)?"
             r"[a-zA-Z0-9_\-?=&]+$" # Slightly improved pattern
        )
        for url in urls_to_download:
             if youtube_pattern.match(url):
                 valid_urls.append(url)
             else:
                 if "://" in url or "." in url: # Heuristic for other URLs
                     valid_urls.append(url)
                     # print(f"Info: Passing potentially non-YouTube URL to yt-dlp: {url}")
                 else:
                     invalid_lines.append(url)

        if not valid_urls:
             messagebox.showerror("Input Error", "No valid-looking URLs found in the input.")
             return

        if invalid_lines:
             max_show = 5
             display_invalid = "\n- ".join(invalid_lines[:max_show])
             if len(invalid_lines) > max_show: display_invalid += "\n- ..."
             messagebox.showwarning("Invalid Lines Skipped",
                                    f"The following lines were skipped (didn't look like URLs):\n- {display_invalid}")


        # --- Start Download ---
        self.is_downloading = True
        self.cancelled = False
        self.set_ui_state(enabled=False) # Disable UI
        self.status_var.set(f"Status: Preparing to process {len(valid_urls)} input URL(s)...")
        self.progress_var.set(0.0)
        self.overall_progress_var.set(f"0/{len(valid_urls)}")

        # Create and start the download thread
        self.download_thread = threading.Thread(
            target=self.download_content,
            args=(valid_urls, download_path, download_type, should_download_playlists, container_format),
            daemon=True
        )
        self.download_thread.start()

    def on_closing(self):
        """Handles the window close event."""
        if self.is_downloading:
            if messagebox.askokcancel("Quit", "Downloads are in progress. Stop downloads and quit?"):
                self.cancelled = True # Set the cancellation flag
                self.update_status("Cancellation requested, waiting for current operation to stop...")
                self.root.after(200, self._check_thread_and_destroy)
            else:
                return # Don't close
        else:
            self.root.destroy() # Close immediately if not downloading

    def _check_thread_and_destroy(self):
        """Helper for on_closing to destroy the window after attempting cancellation."""
        if self.download_thread and self.download_thread.is_alive():
             # Give it a tiny bit more time maybe?
             self.download_thread.join(timeout=0.2) # Wait briefly for thread exit
             if self.download_thread.is_alive():
                 print("Warning: Download thread still active after cancellation signal and brief wait. Forcing exit.")
        self.root.destroy()


# --- Main Execution ---
if __name__ == "__main__":
    # Check for yt-dlp dependency
    try:
        import yt_dlp
    except ImportError:
        error_message = "Required library 'yt-dlp' not found.\nPlease install it using:\n\npip install yt-dlp"
        print(error_message.replace('\n\n', '\n').replace('\n', '\n  ')) # Console formatting
        try:
            root_check = tk.Tk()
            root_check.withdraw() # Hide the main window
            messagebox.showerror("Dependency Error", error_message)
            root_check.destroy()
        except tk.TclError:
            pass # Ignore if GUI can't be shown for the error
        exit(1) # Exit the script

    # Check for FFmpeg? More complex, rely on runtime errors and the note for now.

    root = tk.Tk()
    app = YouTubeDownloaderApp(root)
    root.mainloop()