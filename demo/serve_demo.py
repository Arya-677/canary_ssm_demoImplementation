"""Local HTTP server to serve the Canary SSM V3 Interactive Demo.

Usage:
    python demo/serve_demo.py [--port 8080]
"""
import argparse
import http.server
import socketserver
import webbrowser
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Serve Canary SSM V3 Demo")
    parser.add_argument("--port", type=int, default=8080, help="Port to serve on (default: 8080)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    demo_dir = Path(__file__).parent.resolve()
    
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args_inner, **kwargs_inner):
            super().__init__(*args_inner, directory=str(demo_dir), **kwargs_inner)

    # Allow port reuse
    socketserver.TCPServer.allow_reuse_address = True

    try:
        with socketserver.TCPServer(("", args.port), Handler) as httpd:
            url = f"http://localhost:{args.port}/index.html"
            print(f"================================================================")
            print(f" Canary SSM V3 Interactive Decision Prototype")
            print(f" Serving at: {url}")
            print(f" Press Ctrl+C to stop.")
            print(f"================================================================")
            if not args.no_browser:
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    main()
