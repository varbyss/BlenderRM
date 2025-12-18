# Blender Render Manager

 **Blender Render Manager** is a Python-based utility built with CustomTkinter [cite: 7, 16] designed to streamline the rendering process for 3D artists.  It provides a centralized interface to manage multiple `.blend` files, automate batch rendering, and stay updated through real-time notifications[cite: 8, 47, 98].

---

## 🚀 Key Features

*  **Queue Management:** Add multiple Blender files to a queue, reorder them, and track their status (Pending, Rendering, Done, or Failed)[cite: 47, 48, 52].
*  **Discord Integration:** Receive real-time updates via Discord webhooks that include progress bars, frame counts, and estimated time remaining[cite: 84, 87, 91].
*  **Live Preview & Logs:** View live terminal output directly in the app and see real-time image previews of the frames being rendered[cite: 37, 38, 54, 96].
*  **Auto-Restart & Recovery:** Includes an optional crash detection system that can automatically restart the render process up to 5 times if an error occurs[cite: 65, 72].
*  **Smart Resuming:** Automatically scans your output directory to identify the last rendered frame and skips completed frames to save time[cite: 65, 81, 82].
*  **Customizable Progress Templates:** Use dynamic placeholders like `{bar}`, `{pct}`, and `{est}` to format how progress looks in your Discord channel[cite: 29, 30, 88].

---

## 🛠 Configuration

The application allows you to customize your rendering environment through the **Settings** tab:

| Setting | Description |
| :--- | :--- |
| **Blender Path** |  The file path to your `blender.exe` executable[cite: 23]. |
| **Webhook URL** |  Your unique Discord Webhook URL for remote monitoring[cite: 24, 99]. |
| **Batch Limit** |  Limit the number of projects rendered in a session[cite: 26, 62]. |
| **Templates** |  Customize the Discord message title and body using dynamic syntax[cite: 27, 28, 90]. |

---

## 📖 How to Use

1.   **Set Up:** Open the **Settings** tab and select your Blender executable path[cite: 23, 40].
2.   **Build Queue:** Switch to the **Render Queue** tab and use "Add File" to select your `.blend` projects[cite: 34, 47].
3.   **Monitor:** Go to the **Live Logs** tab to enable image previews and watch the terminal output[cite: 36, 37, 38].
4.   **Render:** Click **START RENDER** in the sidebar to begin processing the queue[cite: 17, 60].

---

## 💻 Installation

1.   **Clone/Download:** Save `BRM.pyw` and your logo file (`512x512logo.png`) in the same directory[cite: 8, 9].
2.  **Install Dependencies:** Run the following command in your terminal:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run:** Launch the app by running:
    ```bash
    python BRM.pyw
    ```
