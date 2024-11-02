# Server Launcher

A simple utility to launch and manage a Python server using Windows scripts, designed for intranet deployment.

## Overview

This project provides scripts to start and manage a Python server in the background using Windows batch and VBScript files. It's specifically designed for intranet environments and uses only Python standard libraries to ensure maximum compatibility without external dependencies.

## Requirements

- Windows operating system
- Python 3.8
- Permission to execute scripts on your system

No additional Python packages are required as this project only uses standard libraries.

## Files

- `start_server.bat` - Batch script to initialize and start the Python server. you need to edit the script to point to the correct Python interpreter and the server script.
- `start_hidden.vbs` - VBScript to run the server process in the background. you need to edit the script to point to the right path of the start_server.bat script.
- `README.md` - Project documentation (this file)

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
