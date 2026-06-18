NEW-RUN REVIEW TOOL
===================
Shows each clip's ORIGINAL next to its 4 takes, side by side.

HOW TO USE
1. Copy these files into the "CPR story lines" folder
   (the folder that contains "_newrun_out" and the clip subfolders
   like "In the City", "Cube Hunters Foraging", etc.).
   The tool uses RELATIVE paths, so it must sit in that folder.
2. Launch it (Python 3 must be installed):
     Windows : double-click  review_windows.bat
     Mac     : double-click  review_mac.command
     Linux   : run           ./review_linux.sh
   It starts a tiny local web server and opens your browser.
3. Each row = one clip:  ORIGINAL | take 1 | take 2 | take 3 | take 4
   Top bar: Play all / Pause all, and a speed selector (0.25x to inspect motion).
4. Close the terminal window the launcher opened to stop the server.

NOTE: opening review.html directly (file://) may not play videos in some
browsers — use the launcher (it serves over http://localhost:8765).
