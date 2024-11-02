# Server Launcher

A simple utility to launch and manage a Python server using Windows scripts, designed for intranet deployment.

## Overview

This project provides scripts to start and manage a Python server in the background using Windows batch and VBScript files. It's specifically designed for intranet environments and uses only Python standard libraries to ensure maximum compatibility without external dependencies. **8000 is the port number, you can change it to any other port number in the server.py file.**

## Requirements

- Windows operating system
- Python 3.8
- Permission to execute scripts on your system

No additional Python packages are required as this project only uses standard libraries.

## Files

- `start_server.bat` - Batch script to initialize and start the Python server. you need to edit the script to point to the correct Python interpreter and the server script.
- `start_hidden.vbs` - VBScript to run the server process in the background. you need to edit the script to point to the right path of the start_server.bat script.
- `README.md` - Project documentation (this file)
- `pages` - This folder contains the markdown files that will be displayed on the intranet.
- `example.md` - This is an example of a markdown file that you can use as a template for your own pages. for images and links, you can use the relative path from the `static` folder, and the format of these files please refer to the tech_python.md file.

## Usage

1. Ensure Python 3.8 is installed on your system
2. Make sure all files are in the same directory
3. Double-click `start_hidden.vbs` to launch the server in background mode
   - Alternatively, run `start_server.bat` directly to see the console output

## Intranet Deployment

This server is designed to run in an intranet environment. It doesn't require internet connectivity or external dependencies, making it suitable for:
- Internal corporate networks
- Isolated network environments
- Environments with strict security requirements

## License

[Add your license information here]

## Contributing

Feel free to open issues or submit pull requests if you have suggestions for improvements.

## release note

- v1.0 2024-11-02: Initial release.

- v1.1 2024-11-02: Added support for two-level classification tags and created example.md as a template for posts.