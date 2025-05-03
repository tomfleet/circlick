import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk
import threading
import json  # Import JSON module for exporting data

class PointCounter:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Point Counter")
        self.points = []
        self.image_scale_factor = 1  # Track the current scale factor of the image
        self.start_x = None  # Track the x-coordinate of the click-down position
        self.start_y = None  # Track the y-coordinate of the click-down position
        self.default_radius = 9  # Default marker radius
        self.in_new_marker_mode = False  # Track whether we're in "new marker mode"
        self.moving_marker = None  # Track the marker being moved
        self.moving_marker_original_coords = None  # Store original coordinates during move
        self.hovered_marker = None  # Track the currently hovered marker
        
        # Select image or JSON file
        file_path = filedialog.askopenfilename(
            filetypes=[("Image or JSON files", "*.png *.jpg *.jpeg *.bmp *.json")]
        )
        if not file_path:
            self.root.destroy()
            return

        # Create a frame to hold the canvas and status bar
        self.frame = tk.Frame(self.root)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Create canvas
        self.canvas = tk.Canvas(self.frame)
        self.canvas.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        # Create status bar
        self.status_bar = tk.Frame(self.frame)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # Add status label to the left
        self.status_label = tk.Label(self.status_bar, text="Points: 0", anchor="w")
        self.status_label.pack(fill=tk.X, side=tk.LEFT, expand=True)

        # Add export button to the right
        self.export_button = tk.Button(self.status_bar, text="Export Markers", command=self.export_markers)
        self.export_button.pack(side=tk.RIGHT)

        # Add import button to the right of the export button
        self.import_button = tk.Button(self.status_bar, text="Import Markers", command=self.import_markers)
        self.import_button.pack(side=tk.RIGHT)

        # Ensure canvas is created before adding markers
        if file_path.endswith(".json"):
            with open(file_path, "r") as f:
                marker_data = json.load(f)

            # Load the image specified in the JSON file
            image_path = marker_data["image_file"]
            self.image = Image.open(image_path)
            self.original_image = self.image.copy()  # Keep a copy of the original image for resizing

            # Update the image scale factor and window dimensions
            self.image_scale_factor = marker_data["image_scale_factor"]
            self.root.geometry(f'{marker_data["window_width"]}x{marker_data["window_height"]}')

            # Clear existing markers
            for point, text, _, _ in self.points:
                self.canvas.delete(point)
                self.canvas.delete(text)
            self.points = []

            # Add markers from the JSON data
            for marker in marker_data["markers"]:
                orig_x, orig_y = marker["initial_position"]["x"], marker["initial_position"]["y"]
                initial_radius = marker["initial_size"]
                scaled_x = orig_x * self.image_scale_factor
                scaled_y = orig_y * self.image_scale_factor
                scaled_radius = initial_radius * self.image_scale_factor

                # Draw the marker on the canvas
                point = self.canvas.create_oval(
                    scaled_x - scaled_radius, scaled_y - scaled_radius,
                    scaled_x + scaled_radius, scaled_y + scaled_radius,
                    fill='green', tags="point"
                )
                text = self.canvas.create_text(scaled_x + 10, scaled_y + 10, text=str(len(self.points) + 1), fill='green', tags="point")

                # Store the marker in the points list
                self.points.append((point, text, (orig_x, orig_y), initial_radius))
        else:
            # Load image directly if not a JSON file
            self.image = Image.open(file_path)
            self.original_image = self.image.copy()  # Keep a copy of the original image for resizing

        # Track previous canvas size
        self.previous_width = None
        self.previous_height = None

        # Calculate the aspect ratio of the image
        self.image_aspect_ratio = self.original_image.width / self.original_image.height

        # Set the initial window size based on the image dimensions
        initial_width = min(self.original_image.width, self.root.winfo_screenwidth() // 2)
        initial_height = int(initial_width / self.image_aspect_ratio)
        self.root.geometry(f"{initial_width}x{initial_height}")

        # Bind the Configure event to enforce aspect ratio
        self.root.bind("<Configure>", self.enforce_aspect_ratio)

        # Display image
        self.update_image()

        # Initialize resize debounce timer
        self.resize_timer = None

        # Bind events
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<ButtonRelease-1>", self.end_drag)
        self.root.bind("<BackSpace>", self.remove_last_point)
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.bind("<Configure>", self.on_resize)
        self.root.bind("d", self.delete_hovered_marker)  # Bind 'd' key to delete hovered marker

        # Bind right mouse events for moving markers
        self.canvas.bind("<ButtonPress-3>", self.start_move_marker)
        self.canvas.bind("<ButtonRelease-3>", self.end_move_marker)

        # Bind mouse motion to track hover events
        self.canvas.bind("<Motion>", self.on_mouse_move)

    def enforce_aspect_ratio(self, event):
        # Prevent recursion by ignoring internal resizing
        if hasattr(self, "_resizing") and self._resizing:
            return

        self._resizing = True  # Set resizing flag

        # Get the new dimensions
        new_width = event.width
        new_height = event.height

        # Calculate the correct height based on the aspect ratio
        correct_height = int(new_width / self.image_aspect_ratio)

        # If the height doesn't match the aspect ratio, adjust it
        if new_height != correct_height:
            self.root.geometry(f"{new_width}x{correct_height}")

        self._resizing = False  # Reset resizing flag

    def update_image(self):
        # Get current window size
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # Check if the window size has changed
        if canvas_width == self.previous_width and canvas_height == self.previous_height:
            return  # No need to redraw if size hasn't changed

        # Update previous size
        self.previous_width = canvas_width
        self.previous_height = canvas_height

        if canvas_width > 1 and canvas_height > 1:  # Avoid resizing to zero during initialization
            # Scale image to fit window while maintaining aspect ratio
            scale_factor = min(canvas_width / self.original_image.width, canvas_height / self.original_image.height)
            self.image_scale_factor = scale_factor  # Update the current image scale factor
            new_width = int(self.original_image.width * scale_factor)
            new_height = int(self.original_image.height * scale_factor)
            resized_image = self.original_image.resize((new_width, new_height), Image.LANCZOS)

            # Update canvas image
            self.photo = ImageTk.PhotoImage(resized_image)
            self.canvas.delete("image")  # Remove any existing image layer
            self.canvas.create_image(0, 0, anchor='nw', image=self.photo, tags="image")

        # Update marker positions to scale with the image
        self.scale_markers()

        # Ensure points are redrawn on top
        self.redraw_points()
        
    def scale_markers(self):
        # Scale all marker positions and sizes based on the image's current scale factor
        for i, (point, text, original_coords, initial_radius) in enumerate(self.points):
            # Calculate new marker positions based on the original image coordinates
            orig_x, orig_y = original_coords
            scaled_x = orig_x * self.image_scale_factor
            scaled_y = orig_y * self.image_scale_factor
            scaled_radius = initial_radius * self.image_scale_factor  # Use initial radius for scaling

            # Update marker positions with scaled size
            self.canvas.coords(
                point,
                scaled_x - scaled_radius, scaled_y - scaled_radius,
                scaled_x + scaled_radius, scaled_y + scaled_radius
            )
            self.canvas.coords(text, scaled_x + 10, scaled_y + 10)

    def update_window_title(self):
        # Update the window title with the current point count
        self.root.title(f"Point Counter - Points: {len(self.points)}")

    def update_status_bar(self):
        # Update the status bar with the current point count
        self.status_label.config(text=f"Points: {len(self.points)}")

    def redraw_points(self):
        # Ensure points are redrawn on top of the image
        for point, text, _, _ in self.points:  # Unpack all four values
            self.canvas.tag_raise(point)
            self.canvas.tag_raise(text)
            # Update the window title
            self.update_window_title()

        # Explicitly raise all points above the image
        self.canvas.tag_lower("image")
        self.canvas.tag_raise("point")

        # Update the status bar
        self.update_status_bar()

    def on_resize(self, event):
        # Cancel any existing timer
        if self.resize_timer:
            self.resize_timer.cancel()

        # Set a new timer to delay the redraw
        self.resize_timer = threading.Timer(0.2, self.check_and_redraw)
        self.resize_timer.start()

    def check_and_redraw(self):
        # Only redraw if the window size has changed
        self.update_image()

    def on_resize_complete(self, event):
        # Ensure the image is updated when resizing is complete
        if self.resize_timer:
            self.resize_timer.cancel()
        self.check_and_redraw()

    def start_drag(self, event):
        # Prohibit mouse down events outside the image dimensions
        if event.x < 0 or event.y < 0 or event.x > self.photo.width() or event.y > self.photo.height():
            print("Click outside image bounds. Ignoring.")
            return

        # Enter "new marker mode" on mouse down
        if self.in_new_marker_mode:
            print("Already in new marker mode. Ignoring additional mouse down.")
            return  # Prevent re-entrance

        self.in_new_marker_mode = True  # Set the flag to indicate we're in "new marker mode"
        self.start_x = event.x
        self.start_y = event.y

        # Convert to image coordinate space
        scaled_x, scaled_y = self.start_x / self.image_scale_factor, self.start_y / self.image_scale_factor

        # Add a temporary marker to the points array with a placeholder radius
        self.points.append((None, None, (scaled_x, scaled_y), 0))  # Placeholder for radius

        # Draw a crosshair at the mouse-down location
        self.crosshair = [
            self.canvas.create_line(event.x - 10, event.y, event.x + 10, event.y, fill="black", tags="temp"),
            self.canvas.create_line(event.x, event.y - 10, event.x, event.y + 10, fill="black", tags="temp")
        ]

        # Draw a shaded circle that will dynamically resize
        self.shaded_circle = self.canvas.create_oval(
            event.x, event.y, event.x, event.y, fill="gray", stipple="gray50", tags="temp"
        )

        # Bind mouse motion to dynamically resize the shaded circle
        self.canvas.bind("<Motion>", self.on_drag)

    def on_drag(self, event):
        # Update the shaded circle's radius based on the current mouse position
        dx = (event.x - self.start_x) / self.image_scale_factor
        dy = (event.y - self.start_y) / self.image_scale_factor
        radius = max(1, int((dx**2 + dy**2)**0.5))  # Ensure radius is at least 1

        # Convert the radius back to canvas coordinates using the image scale factor
        scaled_radius = radius * self.image_scale_factor

        # Update the shaded circle's size
        self.canvas.coords(
            self.shaded_circle,
            self.start_x - scaled_radius, self.start_y - scaled_radius,
            self.start_x + scaled_radius, self.start_y + scaled_radius
        )

        # Update the radius in the temporary marker
        self.points[-1] = (None, None, self.points[-1][2], radius)  # Store unscaled radius

    def end_drag(self, event):
        # Finalize the marker and exit "new marker mode"
        if not self.in_new_marker_mode:
            print("Not in new marker mode. Ignoring mouse up.")
            return  # Ignore if not in "new marker mode"

        if self.start_x is not None and self.start_y is not None:
            # Get the finalized radius in image coordinates
            dx = (event.x - self.start_x) / self.image_scale_factor
            dy = (event.y - self.start_y) / self.image_scale_factor
            radius = max(1, int((dx**2 + dy**2)**0.5))  # Ensure radius is at least 1

            # Update the marker in the points array
            scaled_x, scaled_y = self.start_x / self.image_scale_factor, self.start_y / self.image_scale_factor
            self.points[-1] = (None, None, (scaled_x, scaled_y), radius)  # Store radius in image coordinates

            # Check for overlapping markers
            conflicting_marker = self.is_overlapping(self.start_x, self.start_y, radius * self.image_scale_factor)
            if conflicting_marker:
                # Draw the new marker temporarily for flashing
                new_marker = self.canvas.create_oval(
                    self.start_x - radius * self.image_scale_factor, self.start_y - radius * self.image_scale_factor,
                    self.start_x + radius * self.image_scale_factor, self.start_y + radius * self.image_scale_factor,
                    fill="green", tags="temp"
                )
                # Flash the conflicting markers
                self.flash_conflicting_markers(new_marker, conflicting_marker)
                self.points.pop()  # Remove the temporary marker
            else:
                # Add the finalized marker
                self.add_point(self.start_x, self.start_y, radius * self.image_scale_factor)

        # Remove the temporary crosshair and shaded circle
        self.canvas.delete("temp")

        # Unbind the mouse motion event
        self.canvas.unbind("<Motion>")

        # Reset the drag start position
        self.start_x = None
        self.start_y = None

        # Leave "new marker mode"
        self.in_new_marker_mode = False  # Reset the flag
        print("Exited new marker mode.")

    def flash_conflicting_markers(self, new_marker, conflicting_marker):
        # Temporarily change the color of the conflicting markers
        self.canvas.itemconfig(new_marker, fill="red")
        self.canvas.itemconfig(conflicting_marker, fill="red")

        # Restore the original color after 500ms
        self.root.after(500, lambda: self.canvas.delete(new_marker))  # Remove the new marker
        self.root.after(500, lambda: self.canvas.itemconfig(conflicting_marker, fill="green"))  # Restore existing marker

    def is_overlapping(self, x, y, radius):
        # Scale the new marker's position and radius using the image scale factor
        scaled_x = x / self.image_scale_factor
        scaled_y = y / self.image_scale_factor
        scaled_radius = radius / self.image_scale_factor

        # Check if the new marker overlaps with any existing marker
        for point, _, (orig_x, orig_y), existing_radius in self.points:
            # Exclude the marker being moved from collision detection
            if self.moving_marker and point == self.moving_marker[0]:
                continue

            # Use the original coordinates and radius of the existing marker
            dx = scaled_x - orig_x
            dy = scaled_y - orig_y
            distance = (dx**2 + dy**2)**0.5

            # Check if the distance is less than the sum of the radii
            if distance < (scaled_radius + existing_radius):
                return point  # Return the conflicting marker
        return None

    def add_point(self, x, y, radius=None):
        # Calculate marker position relative to the original image dimensions
        scaled_x, scaled_y = x / self.image_scale_factor, y / self.image_scale_factor
        original_coords = (scaled_x, scaled_y)

        # Use the provided radius or the default radius
        radius = radius if radius is not None else self.default_radius

        # Check for overlapping markers
        if self.is_overlapping(x, y, radius):
            print("Marker overlaps with an existing marker. Skipping placement.")
            return  # Skip placing the marker

        # Draw point and number
        point_num = len(self.points) + 1
        point = self.canvas.create_oval(
            x - radius, y - radius, x + radius, y + radius, fill='green', tags="point"
        )
        text = self.canvas.create_text(x + 10, y + 10, text=str(point_num), fill='green', tags="point")

        # Store the point with its original coordinates and initial radius
        self.points[-1] = (point, text, original_coords, radius / self.image_scale_factor)  # Store unscaled radius
        self.redraw_points()  # Ensure new points are on top

        # Update the status bar
        self.update_status_bar()

    def remove_last_point(self, event):
        if self.points:
            point, text, _, _ = self.points.pop()  # Unpack all four values
            self.canvas.delete(point)
            self.canvas.delete(text)

            # Update the window title
            self.update_window_title()

            # Update the status bar
            self.update_status_bar()

    def export_markers(self):
        # Extract file name and directory location
        image_file_path = self.image.filename
        image_directory = "/".join(image_file_path.split("/")[:-1])
        image_file_name = image_file_path.split("/")[-1]
        json_file_name = image_file_name.rsplit(".", 1)[0] + "_markers.json"
        json_file_path = f"{image_directory}/{json_file_name}"

        # Generate a JSON-like structure of the marker data
        marker_data = {
            "image_file": self.image.filename,
            "image_scale_factor": self.image_scale_factor,
            "window_width": self.canvas.winfo_width(),
            "window_height": self.canvas.winfo_height(),
            "markers": []
        }

        for index, (point, text, original_coords, initial_radius) in enumerate(self.points):
            orig_x, orig_y = original_coords
            scaled_x = orig_x * self.image_scale_factor
            scaled_y = orig_y * self.image_scale_factor
            scaled_radius = initial_radius * self.image_scale_factor

            marker_data["markers"].append({
                "index": index,
                "initial_position": {"x": orig_x, "y": orig_y},
                "initial_size": initial_radius,
                "current_image_scale": self.image_scale_factor,
                "scaled_position": {"x": scaled_x, "y": scaled_y},
                "scaled_size": scaled_radius
            })

        # Save the JSON data to a file in the image directory
        with open(json_file_path, "w") as f:
            json.dump(marker_data, f, indent=4)

        print(f"Markers exported to {json_file_path}")

    def import_markers(self):
        # Open a file dialog to select the JSON file
        json_path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")],
            title="Select Marker JSON File"
        )
        if not json_path:
            return  # Do nothing if no file is selected

        # Load the JSON data
        with open(json_path, "r") as f:
            marker_data = json.load(f)

        # Load the image specified in the JSON file
        image_path = marker_data["image_file"]
        self.image = Image.open(image_path)
        self.original_image = self.image.copy()  # Keep a copy of the original image for resizing

        # Update the image scale factor and window dimensions
        self.image_scale_factor = marker_data["image_scale_factor"]
        self.root.geometry(f'{marker_data["window_width"]}x{marker_data["window_height"]}')

        # Clear existing markers
        for point, text, _, _ in self.points:
            self.canvas.delete(point)
            self.canvas.delete(text)
        self.points = []

        # Add markers from the JSON data
        for marker in marker_data["markers"]:
            orig_x, orig_y = marker["initial_position"]["x"], marker["initial_position"]["y"]
            initial_radius = marker["initial_size"]
            scaled_x = orig_x * self.image_scale_factor
            scaled_y = orig_y * self.image_scale_factor
            scaled_radius = initial_radius * self.image_scale_factor

            # Draw the marker on the canvas
            point = self.canvas.create_oval(
                scaled_x - scaled_radius, scaled_y - scaled_radius,
                scaled_x + scaled_radius, scaled_y + scaled_radius,
                fill='green', tags="point"
            )
            text = self.canvas.create_text(scaled_x + 10, scaled_y + 10, text=str(marker["index"] + 1), fill='green', tags="point")

            # Store the marker in the points list
            self.points.append((point, text, (orig_x, orig_y), initial_radius))

        # Update the canvas and status bar
        self.update_image()
        self.update_status_bar()

    def start_move_marker(self, event):
        # Prohibit mouse down events outside the image dimensions
        if event.x < 0 or event.y < 0 or event.x > self.photo.width() or event.y > self.photo.height():
            print("Click outside image bounds. Ignoring.")
            return

        # Check if a marker is clicked
        clicked_marker = self.get_marker_at(event.x, event.y)
        if clicked_marker:
            self.moving_marker = clicked_marker
            self.moving_marker_original_coords = self.canvas.coords(clicked_marker[0])  # Store original coords

            # Change marker to shaded fill
            self.canvas.itemconfig(self.moving_marker[0], fill="gray", stipple="gray50")
            self.canvas.itemconfig(self.moving_marker[1], fill="gray")

            # Bind motion to move the marker
            self.canvas.bind("<Motion>", self.on_move_marker)

    def on_move_marker(self, event):
        if self.moving_marker:
            # Reset hover state while moving a marker
            if self.hovered_marker:
                self.canvas.itemconfig(self.hovered_marker[0], fill="green", stipple="")
                self.hovered_marker = None

            # Update marker position dynamically
            x, y = event.x, event.y
            radius = (self.moving_marker_original_coords[2] - self.moving_marker_original_coords[0]) / 2
            self.canvas.coords(
                self.moving_marker[0],
                x - radius, y - radius,
                x + radius, y + radius
            )
            self.canvas.coords(self.moving_marker[1], x + 10, y + 10)

    def end_move_marker(self, event):
        if self.moving_marker:
            # Finalize the marker position
            x, y = event.x, event.y
            radius = (self.moving_marker_original_coords[2] - self.moving_marker_original_coords[0]) / 2
            scaled_x, scaled_y = x / self.image_scale_factor, y / self.image_scale_factor

            # Check for overlapping markers
            conflicting_marker = self.is_overlapping(x, y, radius)
            if conflicting_marker:
                # Blink to indicate conflict
                self.blink_conflict(self.moving_marker[0], conflicting_marker)

                # Revert to original position if collision is detected
                orig_x1, orig_y1, orig_x2, orig_y2 = self.moving_marker_original_coords
                self.canvas.coords(self.moving_marker[0], orig_x1, orig_y1, orig_x2, orig_y2)
                self.canvas.coords(self.moving_marker[1], orig_x1 + 10, orig_y1 + 10)
            else:
                # Update marker data in points array
                for i, (point, text, original_coords, initial_radius) in enumerate(self.points):
                    if point == self.moving_marker[0]:
                        self.points[i] = (point, text, (scaled_x, scaled_y), initial_radius)
                        break

            # Restore marker to normal color
            self.canvas.itemconfig(self.moving_marker[0], fill="green", stipple="")
            self.canvas.itemconfig(self.moving_marker[1], fill="green")

            # Reset moving marker state
            self.moving_marker = None
            self.moving_marker_original_coords = None

            # Re-bind hover tracking after move operation
            self.canvas.bind("<Motion>", self.on_mouse_move)

            # Redraw points to ensure proper layering
            self.redraw_points()

    def blink_conflict(self, moved_marker, conflicting_marker):
        # Temporarily change the color of the conflicting markers
        self.canvas.itemconfig(moved_marker, fill="red")
        self.canvas.itemconfig(conflicting_marker, fill="red")

        # Restore the original color after 500ms
        self.root.after(500, lambda: self.canvas.itemconfig(moved_marker, fill="gray", stipple="gray50"))
        self.root.after(500, lambda: self.canvas.itemconfig(conflicting_marker, fill="green"))

    def get_marker_at(self, x, y):
        # Check if a point is clicked based on proximity
        for point, text, _, _ in self.points:
            coords = self.canvas.coords(point)
            radius = (coords[2] - coords[0]) / 2
            center_x, center_y = coords[0] + radius, coords[1] + radius
            if (x - center_x)**2 + (y - center_y)**2 <= radius**2:
                return (point, text)
        return None

    def on_mouse_move(self, event):
        # Check if the mouse is over a marker
        hovered_marker = self.get_marker_at(event.x, event.y)

        if hovered_marker != self.hovered_marker:
            # Restore the previous marker's color if the mouse has exited
            if self.hovered_marker:
                self.canvas.itemconfig(self.hovered_marker[0], fill="green", stipple="")
            # Update the hovered marker and change its color
            self.hovered_marker = hovered_marker
            if self.hovered_marker:
                self.canvas.itemconfig(self.hovered_marker[0], fill="gray", stipple="gray50")

    def delete_hovered_marker(self, event):
        if self.hovered_marker:
            # Find the hovered marker in the points list
            for i, (point, text, original_coords, initial_radius) in enumerate(self.points):
                if point == self.hovered_marker[0]:
                    # Delete the marker from the canvas
                    self.canvas.delete(point)
                    self.canvas.delete(text)

                    # Remove the marker from the points list
                    self.points.pop(i)

                    # Update subsequent marker indexes
                    for j in range(i, len(self.points)):
                        marker_point, marker_text, coords, radius = self.points[j]
                        self.canvas.itemconfig(marker_text, text=str(j + 1))  # Update text label
                        self.points[j] = (marker_point, marker_text, coords, radius)  # Update list

                    # Update the status bar and window title
                    self.update_status_bar()
                    self.update_window_title()
                    break

            # Reset the hovered marker state
            self.hovered_marker = None

    def run(self):
        self.root.mainloop()
        print("Total points marked: {}".format(len(self.points)))

if __name__ == "__main__":
    app = PointCounter()
    app.run()