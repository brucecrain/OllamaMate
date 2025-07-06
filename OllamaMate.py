import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import requests
import json

# Define the Ollama API endpoint
OLLAMA_API = "http://localhost:11434"

class OllamaUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ollama Mate")
        self.configure(bg="black")
        self.geometry("400x500")
        self.resizable(False, True)  # Allow vertical resizing

        self.chat_log = ""  # Stores the complete chat history for export
        self.current_stream_text = "" # To build Ollama's response during streaming

        self.model_var = tk.StringVar()
        self.active_model = None # Stores the currently selected model name

        # Set up a protocol for handling window closing
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.create_widgets()
        self.fetch_models()
        
        # Bind model dropdown selection to set active_model
        self.model_dropdown.bind("<<ComboboxSelected>>", self.on_model_select)

    def create_widgets(self):
        # Output text box for chat history - remains at the top after button frame
        self.output_box = tk.Text(self, height=20, bg="black", fg="white", insertbackground='white', wrap="word")
        self.output_box.pack(padx=10, pady=5, fill="both", expand=True)
        self.output_box.configure(state="disabled")  # Start as disabled (read-only)

        # Configure tags for different message styles
        self.output_box.tag_config("user_tag", foreground="#4fc3f7")    # Light blue for "You:"
        self.output_box.tag_config("ollama_tag", foreground="#81c784")  # Light green for "Ollama:"
        self.output_box.tag_config("message_tag", foreground="white")   # White for actual message content
        self.output_box.tag_config("error_tag", foreground="red")       # Red for error messages

        # Prompt entry box - remains just above the buttons
        self.prompt_entry = tk.Entry(self, bg="black", fg="white", insertbackground='white')
        self.prompt_entry.pack(padx=10, pady=5, fill="x")
        self.prompt_entry.bind("<Return>", self.send_prompt) # Bind Enter key to send_prompt

        # Button frame - now includes the model dropdown
        button_frame = tk.Frame(self, bg="black")
        button_frame.pack(pady=5) # This frame will be below the prompt entry

        # Send button
        send_btn = tk.Button(button_frame, text="Send", command=self.send_prompt)
        send_btn.pack(side="left", padx=5)

        # Export Log button
        export_btn = tk.Button(button_frame, text="Export Log", command=self.export_log)
        export_btn.pack(side="left", padx=5)
        
        # Clear Chat button
        clear_btn = tk.Button(button_frame, text="Clear Chat", command=self.clear_chat)
        clear_btn.pack(side="left", padx=5)

        # Model selection dropdown - MOVED HERE, after the other buttons
        # Pack it to the right of the other buttons in the same frame
        self.model_dropdown = ttk.Combobox(button_frame, textvariable=self.model_var, state="readonly")
        self.model_dropdown.pack(side="left", padx=5) # Use side="left" to place it next to other buttons

    def on_model_select(self, event):
        """Sets the active model when a new model is selected from the dropdown."""
        self.active_model = self.model_var.get()
        # Optional: You could append a message to the chat log indicating the selected model.
        # self.append_system_message(f"Selected model: {self.active_model}") # Example of a new system message function

    def fetch_models(self):
        """Fetches available Ollama models from the API and populates the dropdown."""
        try:
            res = requests.get(f"{OLLAMA_API}/api/tags")
            res.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
            models = [m["name"] for m in res.json().get("models", [])]
            self.model_dropdown['values'] = models
            if models:
                self.model_var.set(models[0])  # Select the first model by default
                self.active_model = models[0]  # Set the active model
        except requests.exceptions.ConnectionError as e:
            messagebox.showerror("Connection Error", f"Could not connect to Ollama API: {e}\nPlease ensure Ollama is running.")
        except requests.exceptions.HTTPError as e:
            messagebox.showerror("API Error", f"Failed to fetch models from Ollama API: {e.response.status_code} - {e.response.text}")
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON Error", f"Failed to decode JSON from Ollama API: {e}")
        except Exception as e:
            messagebox.showerror("Model Fetch Error", f"An unexpected error occurred: {str(e)}")

    def send_prompt(self, event=None):
        """Sends the user's prompt to the Ollama model."""
        prompt = self.prompt_entry.get().strip()
        if not prompt:
            return  # Do nothing if prompt is empty
        
        model = self.model_var.get()
        if not model:
            messagebox.showwarning("No Model Selected", "Please select a model from the dropdown first.")
            return

        # Append user's message to UI and chat log
        # Use the new append_entry_to_chat_box for proper tagging
        self.append_entry_to_chat_box("You:", prompt, "user_tag", "message_tag")
        self.chat_log += f"You:\n{prompt}\n" # Add to the full chat log immediately
        self.prompt_entry.delete(0, tk.END) # Clear the input field
        
        self.current_stream_text = "" # Reset for the new streaming response from Ollama
        # Start streaming response in a separate thread to keep UI responsive
        threading.Thread(target=self.stream_response, args=(model, prompt), daemon=True).start()

    def stream_response(self, model, prompt):
        """Streams the response from the Ollama model API."""
        try:
            # Append Ollama's prefix immediately
            # FIX: Use lambda to correctly pass keyword argument through self.after
            self.after(0, lambda: self.append_entry_to_chat_box("Ollama:", "", "ollama_tag", "message_tag", is_streaming_start=True))

            response = requests.post(
                f"{OLLAMA_API}/api/generate",
                json={"model": model, "prompt": prompt, "stream": True},
                stream=True,
                timeout=600  # Set a timeout for the request (10 minutes)
            )
            response.raise_for_status() # Raise an HTTPError for bad responses

            for line in response.iter_lines():
                if line:
                    try:
                        token_data = json.loads(line.decode('utf-8'))
                        token = token_data.get("response", "")
                        self.current_stream_text += token
                        # Update UI with each token received
                        self.after(0, self.update_output_box_streaming, token)
                    except json.JSONDecodeError:
                        # Skip lines that are not complete JSON (can happen with streaming)
                        pass 
            
            # After the stream completes, add the full Ollama response to the chat_log
            self.chat_log += f"Ollama:\n{self.current_stream_text}\n"

        except requests.exceptions.ConnectionError as e:
            self.after(0, self.append_error_message, f"[Connection Error] Could not connect to Ollama. Is it running? {e}\n")
        except requests.exceptions.Timeout as e:
            self.after(0, self.append_error_message, f"[Timeout Error] The request timed out. {e}\n")
        except requests.exceptions.HTTPError as e:
            self.after(0, self.append_error_message, f"[HTTP Error] {e.response.status_code}: {e.response.text}\n")
        except Exception as e:
            self.after(0, self.append_error_message, f"[General Error] An unexpected error occurred: {e}\n")
            
        # Ensure the output box is disabled and scrolled to the end after streaming
        self.after(0, self.finalize_output_box)

    def append_entry_to_chat_box(self, prefix_text, message_text, prefix_tag, message_tag, is_streaming_start=False):
        """
        Appends a full chat entry (prefix + message) to the output box with proper tags and spacing.
        Used for initial user prompts and for starting Ollama's response.
        """
        self.output_box.configure(state="normal")
        
        # Add an extra newline for spacing before a new turn starts
        # Only add if the box is not empty, to avoid leading blank line
        if self.output_box.index("end-1c") != "1.0":
             self.output_box.insert("end", "\n") 
        
        self.output_box.insert("end", prefix_text + "\n", prefix_tag) # Insert prefix and a newline after it
        if not is_streaming_start: # For non-streaming messages (like user's full prompt)
            self.output_box.insert("end", message_text + "\n", message_tag) # Insert the message content
            
        self.output_box.see("end")
        self.output_box.configure(state="disabled")


    def update_output_box_streaming(self, token):
        """Updates the output box incrementally with streaming tokens."""
        self.output_box.configure(state="normal")
        self.output_box.insert("end", token, "message_tag") # Use message_tag for the token text
        self.output_box.see("end")
        # Keep state normal while actively streaming; it will be disabled in finalize_output_box

    def append_error_message(self, text):
        """Appends an error message to the output box."""
        self.output_box.configure(state="normal")
        # Add an extra newline before the error message for clarity
        if self.output_box.index("end-1c") != "1.0":
             self.output_box.insert("end", "\n") 
        self.output_box.insert("end", text, "error_tag")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def finalize_output_box(self):
        """Ensures the output box is disabled and scrolled to the end."""
        self.output_box.configure(state="disabled")
        self.output_box.see("end")

    def clear_chat(self):
        """Clears the chat history in the UI and internal log."""
        if messagebox.askyesno("Clear Chat", "Are you sure you want to clear the entire chat history?"):
            self.output_box.configure(state="normal")
            self.output_box.delete("1.0", tk.END)
            self.output_box.configure(state="disabled")
            self.chat_log = ""
            messagebox.showinfo("Chat Cleared", "The chat history has been cleared.")

    def export_log(self):
        """Exports the current chat log to a text file."""
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")])
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.chat_log)
                messagebox.showinfo("Export", "Chat log saved successfully.")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to save chat log: {str(e)}")

    def on_close(self):
        """Handles actions when the window is closed."""
        self.destroy()

if __name__ == "__main__":
    app = OllamaUI()
    app.mainloop()