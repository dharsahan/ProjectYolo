import os

def test_phase1():
    vendor_dir = "desktop/renderer/vendor/"
    expected_files = [
        "marked.min.js",
        "highlight.min.js",
        "github-dark.min.css",
        "motion.js"
    ]
    
    print("Checking for vendor files...")
    for f in expected_files:
        path = os.path.join(vendor_dir, f)
        if os.path.exists(path):
            print(f" [OK] {f} exists at {path}")
        else:
            print(f" [FAIL] {f} NOT FOUND at {path}")
            exit(1)
            
    print("\nChecking index.html for CDN URLs...")
    index_path = "desktop/renderer/index.html"
    with open(index_path, "r") as f:
        content = f.read()
        
    cdns = ["cdn.jsdelivr.net", "cdnjs.cloudflare.com"]
    # We only care about the libraries we replaced, but the instruction is broad.
    # However, fonts might still use CDNs (Google Fonts).
    # The instruction says: "does NOT contain 'cdn.jsdelivr.net' or 'cdnjs.cloudflare.com' for these libraries."
    
    for cdn in cdns:
        if cdn in content:
            # Check if it's for the libraries or something else
            lines = [line for line in content.splitlines() if cdn in line]
            for line in lines:
                if any(lib in line for lib in ["marked", "highlight", "motion"]):
                    print(f" [FAIL] Found CDN {cdn} in index.html for a target library: {line.strip()}")
                    exit(1)
                else:
                    print(f" [INFO] Found CDN {cdn} in index.html but not for target libraries: {line.strip()}")
        else:
            print(f" [OK] {cdn} not found in index.html")

    print("\nPhase 1 Verification Successful!")

if __name__ == "__main__":
    test_phase1()
