"""Write the ydotoold user systemd unit file."""
import os

content = "[Unit]\n"
content += "Description=ydotool daemon (user)\n\n"
content += "[Service]\n"
content += "Type=simple\n"
content += "ExecStart=/usr/bin/ydotoold --socket-path=" + "%t" + "/.ydotool_socket --socket-perm=0600\n"
content += "Restart=on-failure\n\n"
content += "[Install]\n"
content += "WantedBy=default.target\n"

path = os.path.expanduser("~/.config/systemd/user/ydotoold.service")
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f:
    f.write(content)
print(f"Written {len(content)} bytes to {path}")

# Verify
with open(path) as f:
    print(f.read())
