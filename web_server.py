import os
import time
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

# Initialize logger
logger = logging.getLogger("web_server")
logging.basicConfig(level=logging.INFO)

def get_db_size():
    db_path = os.getenv("DB_PATH", "lonchera.db")
    if os.path.exists(db_path):
        size_bytes = os.path.getsize(db_path)
        size_mb = size_bytes / (1024 * 1024)
        return f"{size_mb:.2f} MB"
    return "DB not found"

def format_relative_time(seconds):
    intervals = (
        ('weeks', 604800),  # 60 * 60 * 24 * 7
        ('days', 86400),    # 60 * 60 * 24
        ('hours', 3600),    # 60 * 60
        ('minutes', 60),
        ('seconds', 1),
    )

    result = []

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append(f"{int(value)} {name}")

    if not result:
        result.append("just started")

    return ', '.join(result) + ' ago'

start_time = time.time()

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            db_size = get_db_size()
            uptime_seconds = time.time() - start_time
            uptime = format_relative_time(uptime_seconds)
            
            version = os.getenv("VERSION")
            version_info = f"<p>version: {version}</p>" if version else ""
            
            commit = os.getenv("COMMIT")
            commit_link = f'<a href="https://git.sr.ht/~knur/lonchera/commit/{commit}">{commit}</a>' if commit else ""
            commit_info = f"<p>commit: {commit_link}</p>" if commit else ""
            
            bot_status = "running" if application_running() else "stopped"
            response = f"""
            <html>
            <head>
            <title>lonchera</title>
            <link rel="stylesheet" href="https://unpkg.com/sakura.css/css/sakura.css" media="screen" />
            <link rel="stylesheet" href="https://unpkg.com/sakura.css/css/sakura-dark.css" media="screen and (prefers-color-scheme: dark)" />
            <style>
                body {{
                    font-family: monospace;
                }}
            </style>
            </head>
            <body>
                <h1>#status</h1>
                <p>db size: {db_size}</p>
                <p>uptime: {uptime}</p>
                {version_info}
                {commit_info}
                <p>bot status: {bot_status}</p>
            </body>
            </html>
            """
            self.wfile.write(response.encode("utf-8"))

def application_running():
    # Placeholder function to determine if the application is running
    return True

def run_web_server():
    server_address = ("", 8080)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    logger.info("Starting web server on port 8080")
    httpd.serve_forever()