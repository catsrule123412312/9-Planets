import os
import sys
import subprocess
import platform

def check_windows_terminal():
    """Check if Windows Terminal is installed"""
    try:
        result = subprocess.run(['where', 'wt'], capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def launch_windows_terminal():
    """Open Microsoft Store to install Windows Terminal"""
    print("\n" + "="*50)
    print("  Windows Terminal is not installed!")
    print("="*50)
    print("\nThis game requires Windows Terminal to display emojis properly.")
    print("\nOpening Microsoft Store to install Windows Terminal...")
    print("\nAfter installation, run this launcher again!")
    print("\n")
    
    # Open Microsoft Store
    os.system('start ms-windows-store://pdp/?productid=9N0DX20HK701')
    input("Press Enter to exit...")

def main():
    current_os = platform.system()
    
    if current_os == "Windows":
        # Check if Windows Terminal is installed
        if check_windows_terminal():
            # Launch game in Windows Terminal
            print("Launching 9 Planets in Windows Terminal...")
            subprocess.run(['wt.exe', '9Planets.exe'])
        else:
            launch_windows_terminal()
    
    elif current_os == "Darwin":  # macOS
        print("Launching 9 Planets...")
        subprocess.run(['./9Planets'])
    
    elif current_os == "Linux":
        print("Launching 9 Planets...")
        subprocess.run(['./9Planets'])
    
    else:
        print(f"Unsupported operating system: {current_os}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
