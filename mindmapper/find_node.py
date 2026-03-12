import os
import shutil

def find_executable(name):
    # Check PATH
    path = shutil.which(name)
    if path:
        return path
    
    # Check common locations
    common_dirs = [
        "/usr/local/bin",
        "/opt/homebrew/bin",
        "/usr/bin",
        "/bin",
        os.path.expanduser("~/.nvm/current/bin"),
        os.path.expanduser("~/.fnm/current/bin"),
        os.path.expanduser("~/.volta/bin"),
    ]
    
    # Check .nvm specifics if .nvm exists
    nvm_dir = os.path.expanduser("~/.nvm/versions/node")
    if os.path.isdir(nvm_dir):
        for version in os.listdir(nvm_dir):
            bin_path = os.path.join(nvm_dir, version, "bin")
            if os.path.isdir(bin_path):
                common_dirs.append(bin_path)

    for directory in common_dirs:
        exe_path = os.path.join(directory, name)
        if os.path.exists(exe_path) and os.access(exe_path, os.X_OK):
            return exe_path
            
    return None

print(f"Node: {find_executable('node')}")
print(f"Npm: {find_executable('npm')}")
