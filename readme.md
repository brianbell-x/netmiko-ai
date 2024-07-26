# Netmiko AI Chat

Netmiko AI Chat is an advanced interactive command-line interface (CLI) that leverages Anthropic's Claude 3.5 Sonnet model to assist with network engineering tasks, particularly focusing on Netmiko for network automation. This tool combines the power of state-of-the-art language models with practical network automation capabilities, web search functionality, and intelligent code analysis and execution.

## Features

- 💬 Interactive chat interface with Claude 3.5 Sonnet model
- 🌐 Network automation focus using Netmiko
- 🔍 Web search capabilities using Tavily API for up-to-date network information
- 🖥️ Code execution in an isolated Conda environment
- 🔄 Process management for long-running network operations
- 📁 File system operations (read files, list directories)
- 🚀 Automode for efficient autonomous task completion
- 🔢 Iteration tracking and management in automode
- 🎨 Color-coded terminal output using Rich library for improved readability
- 📊 Token usage tracking and visualization
- 💾 Chat log saving capability
- 🖼️ Image analysis capabilities (requires additional setup)

## Installation

1. Clone this repository:
   ```
   git clone <repository-url>
   cd <repository-name>
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up your environment variables:
   - Create a `.env` file in the project root directory
   - Add the following environment variables:
     ```
     ANTHROPIC_API_KEY=your_anthropic_api_key
     TAVILY_API_KEY=your_tavily_api_key
     ```

4. Ensure you have Conda installed on your system, as it's used for creating the isolated environment for code execution.

## Usage

Run the main script to start the Netmiko AI Chat interface:
'''
python main.py
'''

Once started, you can interact with the AI by typing your queries or commands. Some example interactions:

- "Configure a new VLAN on a switch: Create VLAN 100 named 'DevOps' on a Cisco switch and assign it to interface GigabitEthernet1/0/10."
- "Set up OSPF on a router: Configure OSPF process 1 on a Cisco router, advertising networks 192.168.1.0/24 and 10.0.0.0/8 in area 0."
- "Implement port security: Enable port security on interface FastEthernet0/1 of a Cisco switch, allowing a maximum of 2 MAC addresses and configuring violation mode to shutdown."
- "Configure a static route: Add a static route on a Cisco router to reach network 172.16.0.0/16 via next-hop IP 192.168.1.254."
- "Set up Network Time Protocol (NTP): Configure the router to use NTP server 10.0.0.1 as its time source and set the timezone to EST with daylight saving time."

Special commands:
- Type 'exit' to end the conversation and close the application.
- Type 'image' to include an image in your message for analysis (requires additional setup).
- Type 'reset' to reset the entire conversation.
- Type 'automode [number]' to enter Autonomous mode with a specific number of iterations.
- Type 'save chat' to save the current chat log.

## Available Tools

1. execute_code: Run Netmiko scripts in an isolated Conda environment.
2. stop_process: Manage and stop long-running code executions.
3. read_file: Read the contents of a file at the specified path.
4. read_multiple_files: Read the contents of multiple files at specified paths.
5. list_files: List all files and directories in the specified folder.
6. tavily_search: Perform a web search using Tavily API to get up-to-date network information.

## Automode

The automode allows the AI to work autonomously on complex network tasks:

1. Type 'automode [number]' to enter automode with a specific number of iterations.
2. Provide your network-related request when prompted.
3. The AI will work autonomously, providing updates after each iteration.
4. Automode exits when the task is completed, after reaching the maximum number of iterations, or when you press Ctrl+C.

## Error Handling and Recovery

The application implements robust error handling:

- Graceful handling of API errors and network issues
- Automatic retries for transient failures
- Clear error messages and suggestions for user action when needed
- Logging of errors for debugging purposes

## Token Management and Visualization

The application features token management and visualization:

- Display of input, output, and total token usage for each model interaction
- Visualization of remaining context window size

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT License](https://opensource.org/licenses/MIT)