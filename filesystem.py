#!/usr/bin/env python3
"""
filesystem_gui.py
Virtual File System with Tkinter GUI Interface.
"""
import os
import json
import time
import shlex
import tkinter as tk
from tkinter import scrolledtext

# -------------------------
# Configuration
# -------------------------
DISK_FILE = "disk.json"
BLOCK_SIZE = 128
TOTAL_BLOCKS = 128
VALID_STRATEGIES = ("bitmap", "first_fit", "best_fit")

# -------------------------
# Disk persistence helpers
# -------------------------
def default_disk():
    return {
        "blocks": [None] * TOTAL_BLOCKS,
        "files": {},
        "strategy": "bitmap",
        "meta": {"created": time.time()}
    }

def load_disk():
    if not os.path.exists(DISK_FILE):
        d = default_disk()
        save_disk(d)
        return d
    with open(DISK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_disk(disk):
    with open(DISK_FILE, "w", encoding="utf-8") as f:
        json.dump(disk, f, indent=2, ensure_ascii=False)

# -------------------------
# Allocation Strategies
# -------------------------
def free_indices(disk):
    return [i for i, b in enumerate(disk["blocks"]) if b is None]

def get_free_blocks_bitmap(disk, n):
    free = free_indices(disk)
    if len(free) < n:
        return None
    return free[:n]

def get_free_blocks_first_fit(disk, n):
    run = 0
    for i, b in enumerate(disk["blocks"]):
        if b is None:
            run += 1
        else:
            run = 0
        if run == n:
            start = i - n + 1
            return list(range(start, start + n))
    return None

def get_free_blocks_best_fit(disk, n):
    runs, current = [], []
    for i, b in enumerate(disk["blocks"]):
        if b is None:
            current.append(i)
        else:
            if current:
                runs.append(current)
                current = []
    if current:
        runs.append(current)
    candidates = [r for r in runs if len(r) >= n]
    if not candidates:
        return None
    best = min(candidates, key=len)
    return best[:n]

def allocate_blocks(disk, n):
    strat = disk.get("strategy", "bitmap")
    if strat == "bitmap":
        return get_free_blocks_bitmap(disk, n)
    if strat == "first_fit":
        return get_free_blocks_first_fit(disk, n)
    if strat == "best_fit":
        return get_free_blocks_best_fit(disk, n)
    return None

# -------------------------
# File Operations
# -------------------------
def read_file_text(disk, path):
    if path not in disk["files"]:
        raise FileNotFoundError(path)
    pieces = []
    for b in disk["files"][path]:
        piece = disk["blocks"][b] or ""
        pieces.append(piece)
    return "".join(pieces)

def is_contiguous(blocks):
    return all(blocks[i] + 1 == blocks[i+1] for i in range(len(blocks)-1)) if blocks else True

# -------------------------
# Command Executor
# -------------------------
def execute_command(disk, command):
    output = ""
    try:
        parts = shlex.split(command)
    except Exception as e:
        return f"❌ Invalid command: {e}"
    if not parts:
        return ""
    cmd, *args = parts
    cmd = cmd.lower()

    def log(msg):
        nonlocal output
        output += msg + "\n"

    # Commands
    if cmd in ("exit", "quit"):
        save_disk(disk)
        log("💾 Disk saved. You can close the window now.")
    elif cmd == "help":
        log("""
Commands:
  write <path> <content>    Create/overwrite file with content
  append <path> <content>   Append content to file
  cat <path>                View file contents
  rm <path>                 Delete file
  ls                        List all files
  defrag                    Defragment disk
  map                       Show block usage
  strategy <name>           Change allocation strategy
  info                      Show disk info
  help                      Show this help
  exit / quit               Save and exit
""")
    elif cmd == "write":
        if len(args) < 2:
            log("Usage: write <path> <content>")
        else:
            path, content = args[0], " ".join(args[1:])
            blocks_needed = (len(content) + BLOCK_SIZE - 1) // BLOCK_SIZE
            blocks = allocate_blocks(disk, blocks_needed)
            if not blocks:
                log("❌ Not enough space.")
            else:
                for b in disk["files"].get(path, []):
                    disk["blocks"][b] = None
                for i, idx in enumerate(blocks):
                    disk["blocks"][idx] = content[i*BLOCK_SIZE:(i+1)*BLOCK_SIZE]
                disk["files"][path] = blocks
                save_disk(disk)
                log(f"✅ Wrote {len(content)} bytes to {path}")
    elif cmd == "append":
        if len(args) < 2:
            log("Usage: append <path> <content>")
        else:
            path, content = args[0], " ".join(args[1:])
            existing = ""
            if path in disk["files"]:
                existing = read_file_text(disk, path)
            new_content = existing + content
            execute_command(disk, f"write {path} {shlex.quote(new_content)}")
            log(f"✅ Appended to {path}")
    elif cmd == "cat":
        if len(args) != 1:
            log("Usage: cat <path>")
        else:
            try:
                text = read_file_text(disk, args[0])
                log(text if text else "(empty file)")
            except FileNotFoundError:
                log("❌ File not found")
    elif cmd == "rm":
        if len(args) != 1:
            log("Usage: rm <path>")
        else:
            path = args[0]
            if path in disk["files"]:
                for b in disk["files"][path]:
                    disk["blocks"][b] = None
                del disk["files"][path]
                save_disk(disk)
                log(f"🗑️ Deleted {path}")
            else:
                log("❌ File not found")
    elif cmd == "ls":
        if not disk["files"]:
            log("(no files)")
        for name, blocks in disk["files"].items():
            size = sum(len(disk["blocks"][b] or "") for b in blocks)
            frag = "fragmented" if not is_contiguous(blocks) and len(blocks) > 1 else "contiguous"
            log(f"{name:<20} {len(blocks):>3} blocks {size:>5} bytes {frag}")
    elif cmd == "defrag":
        new_blocks = [None] * TOTAL_BLOCKS
        new_map = {}
        idx = 0
        for name, blocks in sorted(disk["files"].items()):
            text = read_file_text(disk, name)
            blocks_needed = (len(text) + BLOCK_SIZE - 1) // BLOCK_SIZE
            assigned = list(range(idx, idx + blocks_needed))
            for i, bi in enumerate(assigned):
                new_blocks[bi] = text[i*BLOCK_SIZE:(i+1)*BLOCK_SIZE]
            new_map[name] = assigned
            idx += blocks_needed
        disk["blocks"] = new_blocks
        disk["files"] = new_map
        save_disk(disk)
        log("✨ Defragmentation complete.")
    elif cmd == "map":
        s = ''.join('1' if b else '0' for b in disk["blocks"])
        for i in range(0, len(s), 64):
            log(s[i:i+64])
    elif cmd == "strategy":
        if len(args) != 1:
            log("Usage: strategy <bitmap|first_fit|best_fit>")
        elif args[0] not in VALID_STRATEGIES:
            log("❌ Invalid strategy.")
        else:
            disk["strategy"] = args[0]
            save_disk(disk)
            log(f"✅ Changed strategy to {args[0]}")
    elif cmd == "info":
        log(json.dumps({
            "strategy": disk.get("strategy"),
            "files": len(disk["files"]),
            "free_blocks": disk["blocks"].count(None)
        }, indent=2))
    else:
        log("❓ Unknown command. Type 'help'.")

    return output.strip()

# -------------------------
# GUI
# -------------------------
def start_gui():
    disk = load_disk()

    root = tk.Tk()
    root.title("Mini Virtual File System")
    root.geometry("800x600")

    tk.Label(root, text="Command:").pack(pady=5)
    cmd_entry = tk.Entry(root, width=100)
    cmd_entry.pack(pady=5)

    output_box = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=100, height=30)
    output_box.pack(pady=10)

    def run_command():
        command = cmd_entry.get().strip()
        if not command:
            return
        output = execute_command(disk, command)
        output_box.insert(tk.END, f"\n> {command}\n{output}\n")
        output_box.see(tk.END)
        cmd_entry.delete(0, tk.END)

    tk.Button(root, text="Run Command", command=run_command).pack(pady=5)
    tk.Button(root, text="Exit & Save", command=lambda: (save_disk(disk), root.destroy())).pack(pady=5)

    root.mainloop()

# -------------------------
# Entry Point
# -------------------------
if __name__ == "__main__":
    start_gui()
