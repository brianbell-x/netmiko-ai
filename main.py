import os
from dotenv import load_dotenv
import json
from tavily import TavilyClient
import base64
from PIL import Image
import io
import re
from anthropic import Anthropic, APIStatusError, APIError
import difflib
import time
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
import asyncio
import aiohttp
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from typing import Optional, Dict, Any

async def get_user_input(prompt="You: "):
    style = Style.from_dict({
        'prompt': 'cyan bold',
    })
    session = PromptSession(style=style)
    return await session.prompt_async(prompt, multiline=False)
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
import datetime
import subprocess
import sys
import logging
from typing import Tuple

def setup_conda_environment() -> Tuple[str, str]:
    conda_env_name = "netmikoai"
    
    try:
        # Check if conda is available
        subprocess.run(["conda", "--version"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        raise EnvironmentError("Conda is not installed or not available in the system PATH.")

    try:
        # Create Conda environment if it doesn't exist
        subprocess.run(["conda", "create", "-n", conda_env_name, "python=3.11", "-y"], check=True)
        
        # Determine the path to the Conda environment
        if sys.platform == "win32":
            env_path = subprocess.check_output(["conda", "env", "list"]).decode().split("\n")
            env_path = [line.split()[1] for line in env_path if conda_env_name in line][0]
            activate_path = os.path.join(env_path, "Scripts", "activate")
        else:
            env_path = os.path.expanduser(f"~/anaconda3/envs/{conda_env_name}")
            activate_path = f"conda activate {conda_env_name}"
        
        # Install Netmiko in the Conda environment
        subprocess.run(["conda", "run", "-n", conda_env_name, "pip", "install", "netmiko"], check=True)
        logging.info("Netmiko has been successfully installed in the Conda environment.")
        
        return env_path, activate_path
    except subprocess.CalledProcessError as e:
        logging.error(f"Error setting up Conda environment: {str(e)}")
        raise

async def execute_code(code, timeout=10):
    global running_processes
    env_path, activate_path = setup_conda_environment()
    
    # Generate a unique identifier for this process
    process_id = f"process_{len(running_processes)}"
    
    # Display the code before writing it to a file
    syntax = Syntax(code, "python", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title="Code to be executed", expand=False))
    
    # Write the code to a temporary file
    with open(f"{process_id}.py", "w") as f:
        f.write(code)
    
    console.print(f"Code written to file: {process_id}.py", style="bold green")
    
    # Prepare the command to run the code
    if sys.platform == "win32":
        command = f'call "{activate_path}" && python "{os.path.join(env_path, "python.exe")}" {process_id}.py'
    else:
        command = f'source ~/.bashrc && {activate_path} && python {process_id}.py'
    
    # Create a process to run the command
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        shell=True,
        preexec_fn=None if sys.platform == "win32" else os.setsid
    )
    
    # Store the process in our global dictionary
    running_processes[process_id] = process
    
    try:
        # Wait for initial output or timeout
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        stdout = stdout.decode()
        stderr = stderr.decode()
        return_code = process.returncode
    except asyncio.TimeoutError:
        # If we timeout, it means the process is still running
        stdout = "Process started and running in the background."
        stderr = ""
        return_code = "Running"
    
    execution_result = f"Process ID: {process_id}\n\nStdout:\n{stdout}\n\nStderr:\n{stderr}\n\nReturn Code: {return_code}"
    return process_id, execution_result

# Load environment variables from .env file
load_dotenv()

# Initialize the Anthropic client
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
if not anthropic_api_key:
    raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
client = Anthropic(api_key=anthropic_api_key)

# Initialize the Tavily client
tavily_api_key = os.getenv("TAVILY_API_KEY")
if not tavily_api_key:
    raise ValueError("TAVILY_API_KEY not found in environment variables")
tavily = TavilyClient(api_key=tavily_api_key)

console = Console()


# Token tracking variables
main_model_tokens = {'input': 0, 'output': 0}
tool_checker_tokens = {'input': 0, 'output': 0}
code_editor_tokens = {'input': 0, 'output': 0}
code_execution_tokens = {'input': 0, 'output': 0}

# Set up the conversation memory (maintains context for MAINMODEL)
conversation_history = []

# Store file contents (part of the context for MAINMODEL)
file_contents = {}

# Code editor memory (maintains some context for CODEEDITORMODEL between calls)
code_editor_memory = []

# Files already present in code editor's context
code_editor_files = set()

# automode flag
automode = False

# Store file contents
file_contents = {}

# Global dictionary to store running processes
running_processes = {}

# Constants
CONTINUATION_EXIT_PHRASE = "AUTOMODE_COMPLETE"
MAX_CONTINUATION_ITERATIONS = 25
MAX_CONTEXT_TOKENS = 200000  # Reduced to 200k tokens for context window

# Models
# Models that maintain context memory across interactions
MAINMODEL = "claude-3-5-sonnet-20240620"  # Maintains conversation history and file contents

# Models that don't maintain context (memory is reset after each call)
TOOLCHECKERMODEL = "claude-3-5-sonnet-20240620"
CODEEDITORMODEL = "claude-3-5-sonnet-20240620"
CODEEXECUTIONMODEL = "claude-3-5-sonnet-20240620"

# System prompts
BASE_SYSTEM_PROMPT = """
You are Claude, an AI assistant powered by Anthropic's Claude-3.5-Sonnet model, specialized in network engineering with a focus on using Netmiko for network automation. Your primary goal is to help users accomplish network engineering tasks effectively and efficiently while maintaining network integrity and security. Your capabilities include:

1. Analyzing and executing network engineering tasks using Netmiko
2. Creating and managing network device configurations
3. Performing network discovery and mapping
4. Implementing security operations and compliance checks
5. Troubleshooting network issues and suggesting solutions
6. Generating and updating network documentation
7. Executing Netmiko scripts in an isolated 'code_execution_env' virtual environment
8. Managing and stopping running processes within the 'code_execution_env'

Available tools and their optimal use cases:

1. execute_code: Run a Netmiko script in the 'code_execution_env' virtual environment and analyze its output. Use this when you need to test script functionality or diagnose issues. This tool returns a process ID for long-running processes.
2. stop_process: Stop a running process by its ID. Use this to terminate a long-running process started by the execute_code tool.
3. read_file: Read the contents of an existing file (e.g., configuration files, logs).
4. read_multiple_files: Read the contents of multiple existing files at once.
5. list_files: List all files and directories in a specified folder.
6. tavily_search: Perform a web search using the Tavily API for up-to-date network engineering information.

Tool Usage Guidelines:
- Always use the most appropriate tool for the task at hand.
- Provide detailed and clear instructions when using tools, especially for configuration changes.
- After making changes, always review the output to ensure accuracy and alignment with intentions.
- Use execute_code to run and test Netmiko scripts within the 'code_execution_env' virtual environment, then analyze the results.
- For long-running processes, use the process ID returned by execute_code to stop them later if needed.
- Proactively use tavily_search when you need up-to-date information on networking concepts, best practices, or vendor-specific details.

Error Handling and Recovery:
- If a tool operation fails, carefully analyze the error message and attempt to resolve the issue.
- If a script execution fails, analyze the error output and suggest potential fixes, considering the isolated nature of the environment.
- If a process fails to stop, consider potential reasons and suggest alternative approaches.

Network Task Analysis and Script Generation:
1. Thoroughly analyze the given network task. If there's not enough information, ask for clarification before proceeding.
2. Think deeply about the planned actions, potential impacts, and necessary precautions before writing any Netmiko script.

 Here are some examples to learn from:
    <examples>
    # This Netmiko script autodetects the device type of a network device, establishes an SSH connection, and retrieves the device prompt. It uses SSHDetect for automatic device type detection and ConnectHandler for secure connection handling.

    from netmiko import SSHDetect, ConnectHandler
    from getpass import getpass

    device = {
        "device_type": "autodetect",
        "host": "cisco1.lasthop.io",
        "username": "pyclass",
        "password": getpass(),
    }

    guesser = SSHDetect(**device)
    best_match = guesser.autodetect()
    print(best_match)  # Name of the best device_type to use further
    print(guesser.potential_matches)  # Dictionary of the whole matching result
    # Update the 'device' dictionary with the device_type
    device["device_type"] = best_match

    with ConnectHandler(**device) as connection:
        print(connection.find_prompt())

    # This Netmiko script connects to a Cisco IOS device, configures logging buffer size, saves the configuration, and prints the output. It uses secure password input and establishes a connection using SSH.

    from netmiko import ConnectHandler
    from getpass import getpass

    device = {
        "device_type": "cisco_ios",
        "host": "cisco1.lasthop.io",
        "username": "pyclass",
        "password": getpass(),
    }

    commands = ["logging buffered 100000"]
    with ConnectHandler(**device) as net_connect:
        output = net_connect.send_config_set(commands)
        output += net_connect.save_config()

    print()
    print(output)
    print()

    # This Netmiko script connects to a Cisco IOS device, executes the 'show ip int brief' command, and prints the cleaned output. It uses secure password input and automatic connection handling.

    from netmiko import ConnectHandler
    from getpass import getpass

    cisco1 = {
        "device_type": "cisco_ios",
        "host": "cisco1.lasthop.io",
        "username": "pyclass",
        "password": getpass(),
    }

    # Show command that we execute
    command = "show ip int brief"
    with ConnectHandler(**cisco1) as net_connect:
        output = net_connect.send_command(command)

    # Automatically cleans-up the output so that only the show output is returned
    print()
    print(output)
    print()

    # This script uses Netmiko to establish an SSH connection to a Cisco IOS device, elevates privileges to enable mode, and prints the device prompt. It securely prompts for the user's password and enable secret.

    from netmiko import ConnectHandler
    from getpass import getpass

    password = getpass()
    secret = getpass("Enter secret: ")

    cisco1 = {
        "device_type": "cisco_ios",
        "host": "cisco1.lasthop.io",
        "username": "pyclass",
        "password": password,
        "secret": secret,
    }

    net_connect = ConnectHandler(**cisco1)
    # Call 'enable()' method to elevate privileges
    net_connect.enable()
    print(net_connect.find_prompt())

    # This Netmiko script connects to a Cisco IOS device, applies configuration changes from a file, saves the configuration, and prints the output. It uses secure password input and file-based configuration management.

    from netmiko import ConnectHandler
    from getpass import getpass

    device1 = {
        "device_type": "cisco_ios",
        "host": "cisco1.lasthop.io",
        "username": "pyclass",
        "password": getpass(),
    }

    # File in same directory as script that contains
    #
    # $ cat config_changes.txt
    # --------------
    # logging buffered 100000
    # no logging console

    cfg_file = "config_changes.txt"
    with ConnectHandler(**device1) as net_connect:
        output = net_connect.send_config_from_file(cfg_file)
        output += net_connect.save_config()

    print()
    print(output)
    print()

    # This Netmiko script connects to a Cisco IOS device, executes the "show ip interface brief" command, and prints the structured output using Genie parser. It demonstrates secure connection handling and command execution on network devices.

    from getpass import getpass
    from pprint import pprint
    from netmiko import ConnectHandler

    device = {
        "device_type": "cisco_ios",
        "host": "cisco1.lasthop.io",
        "username": "pyclass",
        "password": getpass(),
    }

    with ConnectHandler(**device) as net_connect:
        output = net_connect.send_command("show ip interface brief", use_genie=True)

    print()
    pprint(output)
    print()

    # This Netmiko script connects to a Cisco IOS device, deletes a file from its flash memory using the 'delete' command, and handles the interactive prompts automatically. It uses send_command_timing for delay-based interactions and prints the output of the operation.

    from netmiko import ConnectHandler
    from getpass import getpass

    cisco1 = {
        "device_type": "cisco_ios",
        "host": "cisco1.lasthop.io",
        "username": "pyclass",
        "password": getpass(),
    }

    command = "del flash:/test3.txt"
    net_connect = ConnectHandler(**cisco1)

    # CLI Interaction is as follows:
    # cisco1#delete flash:/testb.txt
    # Delete filename [testb.txt]?
    # Delete flash:/testb.txt? [confirm]y

    # Use 'send_command_timing' which is entirely delay based.
    # strip_prompt=False and strip_command=False make the output
    # easier to read in this context.
    output = net_connect.send_command_timing(
        command_string=command, strip_prompt=False, strip_command=False
    )
    if "Delete filename" in output:
        output += net_connect.send_command_timing(
            command_string="\n", strip_prompt=False, strip_command=False
        )
    if "confirm" in output:
        output += net_connect.send_command_timing(
            command_string="y", strip_prompt=False, strip_command=False
        )
    net_connect.disconnect()

    print()
    print(output)
    print()

    # This Netmiko script connects to a Cisco IOS device, deletes a file from its flash memory, and handles the interactive prompts during the deletion process. It demonstrates how to use Netmiko's send_command method with expect_string for managing multi-step CLI interactions.

    from netmiko import ConnectHandler
    from getpass import getpass

    cisco1 = {
        "device_type": "cisco_ios",
        "host": "cisco1.lasthop.io",
        "username": "pyclass",
        "password": getpass(),
    }

    command = "del flash:/test4.txt"
    net_connect = ConnectHandler(**cisco1)

    # CLI Interaction is as follows:
    # cisco1#delete flash:/testb.txt
    # Delete filename [testb.txt]?
    # Delete flash:/testb.txt? [confirm]y

    # Use 'send_command' and the 'expect_string' argument (note, expect_string uses
    # RegEx patterns). Netmiko will move-on to the next command when the
    # 'expect_string' is detected.

    # strip_prompt=False and strip_command=False make the output
    # easier to read in this context.
    output = net_connect.send_command(
        command_string=command,
        expect_string=r"Delete filename",
        strip_prompt=False,
        strip_command=False,
    )
    output += net_connect.send_command(
        command_string="\n",
        expect_string=r"confirm",
        strip_prompt=False,
        strip_command=False,
    )
    output += net_connect.send_command(
        command_string="y", expect_string=r"#", strip_prompt=False, strip_command=False
    )
    net_connect.disconnect()

    print()
    print(output)
    print()

    # This Netmiko script connects to a Cisco IOS device, executes the 'show ip int brief' command using TextFSM for structured output, and prints the results.

    from netmiko import ConnectHandler
    from getpass import getpass
    from pprint import pprint

    cisco1 = {
        "device_type": "cisco_ios",
        "host": "cisco1.lasthop.io",
        "username": "pyclass",
        "password": getpass(),
    }

    command = "show ip int brief"
    with ConnectHandler(**cisco1) as net_connect:
        # Use TextFSM to retrieve structured data
        output = net_connect.send_command(command, use_textfsm=True)

    print()
    pprint(output)
    print()

    </examples>

3. When generating a Netmiko script:
   a. Use the provided device information and task details.
   b. Follow best practices for secure and efficient network management.
   c. After generating the script, identify and list any potential side effects of running it.
   d. Always ask for approval before suggesting to run the script.
4. Provide your response in the following format:
   <analysis>
   Your detailed analysis of the task and any clarifications needed
   </analysis>

   <code>
   Your generated Netmiko python code
   </code>

   <side_effects>
   List of potential side effects from running the script
   </side_effects>

   <approval_request>
   Your request for approval to run the script
   </approval_request>

Always strive for accuracy, clarity, and efficiency in your responses and actions. Your instructions must be precise and comprehensive. If uncertain, use the tavily_search tool or admit your limitations. When executing Netmiko scripts, always remember that they run in the isolated 'code_execution_env' virtual environment. Be aware of any long-running processes you start and manage them appropriately, including stopping them when they are no longer needed.

Remember:
- Always prioritize network safety and security.
- Do not execute scripts without explicit approval.
- If you're unsure about any aspect of the task, ask for clarification.
- Treat Netmiko scripts as powerful tools that require careful handling.
- Consider the potential impact of network changes on the entire infrastructure.
- Stay updated on network engineering best practices and vendor-specific recommendations.

Your primary goal is to assist users in accomplishing their network engineering tasks effectively and efficiently while maintaining the integrity and security of their network environment.
"""

AUTOMODE_SYSTEM_PROMPT = """
    You are currently in automode for network engineering tasks. Follow these guidelines:

    Goal Setting:

    Set clear, achievable network-related goals based on the user's request.
    Break down complex network tasks into smaller, manageable goals.


    Goal Execution:

    Work through goals systematically, using appropriate tools for each network task.
    Utilize Netmiko script execution, file operations, and web searches as needed.
    Always verify device information and connection details before executing scripts.


    Progress Tracking:

    Provide regular updates on network task completion and overall progress.
    Use the iteration information to pace your work effectively, considering potential impact on network operations.


    Tool Usage:

    Leverage all available tools to accomplish your network goals efficiently.
    Use execute_code for device interactions and configurations.
    Utilize read_file and read_multiple_files to examine configuration files or logs.
    Use tavily_search proactively for up-to-date network documentation and best practices.


    Error Handling:

    If a tool operation or script execution fails, analyze the error and attempt to resolve the issue.
    For persistent errors, consider alternative approaches to achieve the network goal.
    Always prioritize network safety and stability when handling errors.


    Automode Completion:

    When all network-related goals are completed, respond with "AUTOMODE_COMPLETE" to exit automode.
    Do not ask for additional tasks or modifications once goals are achieved.


    Iteration Awareness:

    You have access to this {iteration_info}.
    Use this information to prioritize network tasks and manage time effectively.


    Network Safety:

    Always consider the potential impact of your actions on the network.
    Implement changes gradually and verify results after each significant modification.
    If a task seems potentially disruptive, exit automode and seek user confirmation.



    Remember: Focus on completing the established network engineering goals efficiently and effectively. Prioritize network stability and security throughout the process. Avoid unnecessary conversations or requests for additional tasks.
"""


def update_system_prompt(current_iteration: Optional[int] = None, max_iterations: Optional[int] = None) -> str:
    global file_contents
    chain_of_thought_prompt = """
Answer the user's network engineering request using relevant tools (if they are available). Before calling a tool, do some analysis within <thinking></thinking> tags. Follow these steps:

Think about which of the provided tools is most relevant to address the user's network-related request. Consider the specific network task at hand (e.g., configuration, troubleshooting, information gathering).
For the chosen tool, go through each of the required parameters and determine if the user has directly provided or given enough information to infer a value. When deciding if a parameter can be inferred, carefully consider all the context, including any previously mentioned network details or configurations.
If all required parameters are present or can be reasonably inferred, close the thinking tag and proceed with the tool call.
If one or more values for required parameters are missing, DO NOT invoke the function (not even with placeholders for the missing params). Instead, ask the user to provide the specific missing information needed for the network task.
DO NOT ask for more information on optional parameters if it is not provided, unless it's critical for the network operation's safety or success.
When using the execute_code tool, ensure that the script includes all necessary device connection details and is properly structured for safe execution in the isolated environment.
If using the tavily_search tool for network documentation, focus on formulating queries that will yield the most relevant and up-to-date information for the specific network task or issue.

Do not reflect on the quality of the returned search results in your response. Focus on interpreting and applying the information to the user's network engineering request.
    """
    
    file_contents_prompt = "\n\nFile Contents:\n"
    for path, content in file_contents.items():
        file_contents_prompt += f"\n--- {path} ---\n{content}\n"
    
    if automode:
        iteration_info = ""
        if current_iteration is not None and max_iterations is not None:
            iteration_info = f"You are currently on iteration {current_iteration} out of {max_iterations} in automode."
        return BASE_SYSTEM_PROMPT + file_contents_prompt + "\n\n" + AUTOMODE_SYSTEM_PROMPT.format(iteration_info=iteration_info) + "\n\n" + chain_of_thought_prompt
    else:
        return BASE_SYSTEM_PROMPT + file_contents_prompt + "\n\n" + chain_of_thought_prompt

def read_file(path):
    global file_contents
    try:
        with open(path, 'r') as f:
            content = f.read()
        file_contents[path] = content
        return f"File '{path}' has been read and stored in the system prompt."
    except Exception as e:
        return f"Error reading file: {str(e)}"

def read_multiple_files(paths):
    global file_contents
    results = []
    for path in paths:
        try:
            with open(path, 'r') as f:
                content = f.read()
            file_contents[path] = content
            results.append(f"File '{path}' has been read and stored in the system prompt.")
        except Exception as e:
            results.append(f"Error reading file '{path}': {str(e)}")
    return "\n".join(results)

def list_files(path="."):
    try:
        files = os.listdir(path)
        return "\n".join(files)
    except Exception as e:
        return f"Error listing files: {str(e)}"

def tavily_search(query):
    try:
        response = tavily.qna_search(query=query, search_depth="advanced")
        return response
    except Exception as e:
        return f"Error performing search: {str(e)}"

def stop_process(process_id):
    global running_processes
    if process_id in running_processes:
        process = running_processes[process_id]
        if sys.platform == "win32":
            process.terminate()
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        del running_processes[process_id]
        return f"Process {process_id} has been stopped."
    else:
        return f"No running process found with ID {process_id}."


tools = [
    {
        "name": "execute_code",
        "description": "Execute a Netmiko script in the 'code_execution_env' virtual environment and return the output. This tool should be used when you need to run Netmiko scripts and see their output or check for errors. All script execution happens exclusively in this isolated environment. The tool will return the standard output, standard error, and return code of the executed script. Long-running processes will return a process ID for later management.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The Netmiko script to execute in the 'code_execution_env' virtual environment. Include all necessary imports, device connection details, and ensure the script is complete and self-contained."
                }
            },
            "required": ["code"]
        }
    },
    {
        "name": "stop_process",
        "description": "Stop a running process by its ID. This tool should be used to terminate long-running processes that were started by the execute_code tool. It will attempt to stop the process gracefully, but may force termination if necessary. The tool will return a success message if the process is stopped, and an error message if the process doesn't exist or can't be stopped.",
        "input_schema": {
            "type": "object",
            "properties": {
                "process_id": {
                    "type": "string",
                    "description": "The ID of the process to stop, as returned by the execute_code tool for long-running processes."
                }
            },
            "required": ["process_id"]
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file at the specified path. This tool should be used when you need to examine the contents of an existing file. It will return the entire contents of the file as a string. If the file doesn't exist or can't be read, an appropriate error message will be returned.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The absolute or relative path of the file to read. Use forward slashes (/) for path separation, even on Windows systems."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "read_multiple_files",
        "description": "Read the contents of multiple files at the specified paths. This tool should be used when you need to examine the contents of multiple existing files at once. It will return the status of reading each file, and store the contents of successfully read files in the system prompt. If a file doesn't exist or can't be read, an appropriate error message will be returned for that file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "An array of absolute or relative paths of the files to read. Use forward slashes (/) for path separation, even on Windows systems."
                }
            },
            "required": ["paths"]
        }
    },
    {
        "name": "list_files",
        "description": "List all files and directories in the specified folder. This tool should be used when you need to see the contents of a directory. It will return a list of all files and subdirectories in the specified path. If the directory doesn't exist or can't be read, an appropriate error message will be returned.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The absolute or relative path of the folder to list. Use forward slashes (/) for path separation, even on Windows systems. If not provided, the current working directory will be used."
                }
            }
        }
    },
    {
        "name": "tavily_search",
        "description": "Perform a web search using the Tavily API to find up-to-date network documentation, configuration guides, best practices, or troubleshooting information. This tool should be used as a fallback when you need more detailed or current information about specific network devices, protocols, or configurations that may not be in your training data. It's particularly useful for finding vendor-specific documentation, recent changes in network technologies, or detailed configuration examples. The tool will return a summary of the search results, including relevant snippets and source URLs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The network-related search query. Be as specific as possible, including device models, software versions, protocol names, or exact error messages to get the most relevant results. For example: 'Cisco IOS XE 17.3 OSPF configuration guide' or 'Juniper MX Series MPLS troubleshooting'."
                }
            },
            "required": ["query"]
        }
}
]

from typing import Optional, Dict, Any
import asyncio
import logging

async def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = None
        is_error = False

        if tool_name == "execute_code":
            process_id, execution_result = await execute_code(tool_input["code"])
            analysis_task = asyncio.create_task(send_to_ai_for_executing(tool_input["code"], execution_result))
            analysis = await analysis_task
            result = f"{execution_result}\n\nAnalysis:\n{analysis}"
            if process_id in running_processes:
                result += "\n\nNote: The process is still running in the background."
        elif tool_name == "stop_process":
            result = stop_process(tool_input["process_id"])
        elif tool_name == "read_file":
            result = read_file(tool_input["path"])
        elif tool_name == "read_multiple_files":
            result = read_multiple_files(tool_input["paths"])
        elif tool_name == "list_files":
            result = list_files(tool_input.get("path", "."))
        elif tool_name == "tavily_search":
            result = tavily_search(tool_input["query"])
        else:
            is_error = True
            result = f"Unknown tool: {tool_name}"

        return {
            "content": result,
            "is_error": is_error
        }
    except KeyError as e:
        logging.error(f"Missing required parameter {str(e)} for tool {tool_name}")
        return {
            "content": f"Error: Missing required parameter {str(e)} for tool {tool_name}",
            "is_error": True
        }
    except Exception as e:
        logging.error(f"Error executing tool {tool_name}: {str(e)}")
        return {
            "content": f"Error executing tool {tool_name}: {str(e)}",
            "is_error": True
        }
def encode_image_to_base64(image_path):
    try:
        with Image.open(image_path) as img:
            max_size = (1024, 1024)
            img.thumbnail(max_size, Image.DEFAULT_STRATEGY)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG')
            return base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
    except Exception as e:
        return f"Error encoding image: {str(e)}"

def parse_goals(response):
    goals = re.findall(r'Goal \d+: (.+)', response)
    return goals

def execute_goals(goals):
    global automode
    for i, goal in enumerate(goals, 1):
        console.print(Panel(f"Executing Goal {i}: {goal}", title="Goal Execution", style="bold yellow"))
        response, _ = chat_with_claude(f"Continue working on goal: {goal}")
        if CONTINUATION_EXIT_PHRASE in response:
            automode = False
            console.print(Panel("Exiting automode.", title="Automode", style="bold green"))
            break


async def send_to_ai_for_executing(code, execution_result):
    global code_execution_tokens

    try:
        system_prompt = f"""
        You are an AI network engineering assistant specializing in Netmiko script analysis. Your task is to analyze the provided Netmiko script and its execution result from the 'code_execution_env' virtual environment, then provide a concise summary of what worked, what didn't work, and any important observations. Follow these steps:

        1. Review the Netmiko script that was executed in the 'code_execution_env' virtual environment:
        {code}

        2. Analyze the execution result from the 'code_execution_env' virtual environment:
        {execution_result}

        3. Provide a brief summary of:
           - Which network devices were targeted and what operations were performed
           - What parts of the script executed successfully in the virtual environment
           - Any errors or unexpected behavior encountered during the execution
           - Potential improvements or fixes for issues, considering network best practices and common pitfalls
           - Any important observations about the script's performance or output
           - If the execution timed out, explain what this might mean in a network context (e.g., device unresponsive, connection issues)

        Be concise and focus on the most important aspects of the Netmiko script execution within the 'code_execution_env' virtual environment. Consider network-specific implications and potential impact on the targeted devices or network.

        IMPORTANT: PROVIDE ONLY YOUR ANALYSIS AND OBSERVATIONS. DO NOT INCLUDE ANY PREFACING STATEMENTS OR EXPLANATIONS OF YOUR ROLE.
        """

        response = client.messages.create(
            model=CODEEXECUTIONMODEL,
            max_tokens=2000,
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"Analyze this Netmiko script execution from the 'code_execution_env' virtual environment:\n\nScript:\n{code}\n\nExecution Result:\n{execution_result}"}
            ]
        )

        # Update token usage for Netmiko script execution
        code_execution_tokens['input'] += response.usage.input_tokens
        code_execution_tokens['output'] += response.usage.output_tokens

        analysis = response.content[0].text

        return analysis

    except Exception as e:
        console.print(f"Error in AI Netmiko script execution analysis: {str(e)}", style="bold red")
        return f"Error analyzing Netmiko script execution from 'code_execution_env': {str(e)}"


def save_chat():
    # Generate filename
    now = datetime.datetime.now()
    filename = f"Chat_{now.strftime('%H%M')}.md"
    
    # Format conversation history
    formatted_chat = "# Netmiko AI Log\n\n"
    for message in conversation_history:
        if message['role'] == 'user':
            formatted_chat += f"## User\n\n{message['content']}\n\n"
        elif message['role'] == 'assistant':
            if isinstance(message['content'], str):
                formatted_chat += f"## Claude\n\n{message['content']}\n\n"
            elif isinstance(message['content'], list):
                for content in message['content']:
                    if content['type'] == 'tool_use':
                        formatted_chat += f"### Tool Use: {content['name']}\n\n```json\n{json.dumps(content['input'], indent=2)}\n```\n\n"
                    elif content['type'] == 'text':
                        formatted_chat += f"## Claude\n\n{content['text']}\n\n"
        elif message['role'] == 'user' and isinstance(message['content'], list):
            for content in message['content']:
                if content['type'] == 'tool_result':
                    formatted_chat += f"### Tool Result\n\n```\n{content['content']}\n```\n\n"
    
    # Save to file
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(formatted_chat)
    
    return filename



async def chat_with_claude(user_input, image_path=None, current_iteration=None, max_iterations=None):
    global conversation_history, automode, main_model_tokens

    # This function uses MAINMODEL, which maintains context across calls
    current_conversation = []

    if image_path:
        console.print(Panel(f"Processing image at path: {image_path}", title_align="left", title="Image Processing", expand=False, style="yellow"))
        image_base64 = encode_image_to_base64(image_path)

        if image_base64.startswith("Error"):
            console.print(Panel(f"Error encoding image: {image_base64}", title="Error", style="bold red"))
            return "I'm sorry, there was an error processing the image. Please try again.", False

        image_message = {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_base64
                    }
                },
                {
                    "type": "text",
                    "text": f"User input for image: {user_input}"
                }
            ]
        }
        current_conversation.append(image_message)
        console.print(Panel("Image message added to conversation history", title_align="left", title="Image Added", style="green"))
    else:
        current_conversation.append({"role": "user", "content": user_input})

    # Filter conversation history to maintain context
    filtered_conversation_history = []
    for message in conversation_history:
        if isinstance(message['content'], list):
            filtered_content = [
                content for content in message['content']
                if content.get('type') != 'tool_result' or (
                    content.get('type') == 'tool_result' and
                    not any(keyword in content.get('output', '') for keyword in [
                        "File contents updated in system prompt",
                        "File created and added to system prompt",
                        "has been read and stored in the system prompt"
                    ])
                )
            ]
            if filtered_content:
                filtered_conversation_history.append({**message, 'content': filtered_content})
        else:
            filtered_conversation_history.append(message)

    # Combine filtered history with current conversation to maintain context
    messages = filtered_conversation_history + current_conversation

    try:
        # MAINMODEL call, which maintains context
        response = client.messages.create(
            model=MAINMODEL,
            max_tokens=8000,
            system=update_system_prompt(current_iteration, max_iterations),
            extra_headers={"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"},
            messages=messages,
            tools=tools,
            tool_choice={"type": "auto"}
        )
        # Update token usage for MAINMODEL
        main_model_tokens['input'] += response.usage.input_tokens
        main_model_tokens['output'] += response.usage.output_tokens
    except APIStatusError as e:
        if e.status_code == 429:
            console.print(Panel("Rate limit exceeded. Retrying after a short delay...", title="API Error", style="bold yellow"))
            time.sleep(5)
            return await chat_with_claude(user_input, image_path, current_iteration, max_iterations)
        else:
            console.print(Panel(f"API Error: {str(e)}", title="API Error", style="bold red"))
            return "I'm sorry, there was an error communicating with the AI. Please try again.", False
    except APIError as e:
        console.print(Panel(f"API Error: {str(e)}", title="API Error", style="bold red"))
        return "I'm sorry, there was an error communicating with the AI. Please try again.", False

    assistant_response = ""
    exit_continuation = False
    tool_uses = []

    for content_block in response.content:
        if content_block.type == "text":
            assistant_response += content_block.text
            if CONTINUATION_EXIT_PHRASE in content_block.text:
                exit_continuation = True
        elif content_block.type == "tool_use":
            tool_uses.append(content_block)

    console.print(Panel(Markdown(assistant_response), title="Claude's Response", title_align="left", border_style="blue", expand=False))

    # Display files in context
    if file_contents:
        files_in_context = "\n".join(file_contents.keys())
    else:
        files_in_context = "No files in context. Read, create, or edit files to add."
    console.print(Panel(files_in_context, title="Files in Context", title_align="left", border_style="white", expand=False))

    for tool_use in tool_uses:
        tool_name = tool_use.name
        tool_input = tool_use.input
        tool_use_id = tool_use.id

        console.print(Panel(f"Tool Used: {tool_name}", style="green"))
        console.print(Panel(f"Tool Input: {json.dumps(tool_input, indent=2)}", style="green"))

        tool_result = await execute_tool(tool_name, tool_input)
        
        if tool_result["is_error"]:
            console.print(Panel(tool_result["content"], title="Tool Execution Error", style="bold red"))
        else:
            console.print(Panel(tool_result["content"], title_align="left", title="Tool Result", style="green"))

        current_conversation.append({
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": tool_input
                }
            ]
        })

        current_conversation.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": tool_result["content"],
                    "is_error": tool_result["is_error"]
                }
            ]
        })

        # Update the file_contents dictionary if applicable
        if tool_name in ['create_file', 'edit_and_apply', 'read_file'] and not tool_result["is_error"]:
            if 'path' in tool_input:
                file_path = tool_input['path']
                if "File contents updated in system prompt" in tool_result["content"] or \
                   "File created and added to system prompt" in tool_result["content"] or \
                   "has been read and stored in the system prompt" in tool_result["content"]:
                    # The file_contents dictionary is already updated in the tool function
                    pass

        messages = filtered_conversation_history + current_conversation

        try:
            tool_response = client.messages.create(
                model=TOOLCHECKERMODEL,
                max_tokens=8000,
                system=update_system_prompt(current_iteration, max_iterations),
                extra_headers={"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"},
                messages=messages,
                tools=tools,
                tool_choice={"type": "auto"}
            )
            # Update token usage for tool checker
            tool_checker_tokens['input'] += tool_response.usage.input_tokens
            tool_checker_tokens['output'] += tool_response.usage.output_tokens

            tool_checker_response = ""
            for tool_content_block in tool_response.content:
                if tool_content_block.type == "text":
                    tool_checker_response += tool_content_block.text
            console.print(Panel(Markdown(tool_checker_response), title="Claude's Response to Tool Result",  title_align="left", border_style="blue", expand=False))
            assistant_response += "\n\n" + tool_checker_response
        except APIError as e:
            error_message = f"Error in tool response: {str(e)}"
            console.print(Panel(error_message, title="Error", style="bold red"))
            assistant_response += f"\n\n{error_message}"

    if assistant_response:
        current_conversation.append({"role": "assistant", "content": assistant_response})

    conversation_history = messages + [{"role": "assistant", "content": assistant_response}]

    # Display token usage at the end
    display_token_usage()

    return assistant_response, exit_continuation

def reset_code_editor_memory():
    global code_editor_memory
    code_editor_memory = []
    console.print(Panel("Code editor memory has been reset.", title="Reset", style="bold green"))


def reset_conversation():
    global conversation_history, main_model_tokens, tool_checker_tokens, code_editor_tokens, code_execution_tokens, file_contents, code_editor_files
    conversation_history = []
    main_model_tokens = {'input': 0, 'output': 0}
    tool_checker_tokens = {'input': 0, 'output': 0}
    code_editor_tokens = {'input': 0, 'output': 0}
    code_execution_tokens = {'input': 0, 'output': 0}
    file_contents = {}
    code_editor_files = set()
    reset_code_editor_memory()
    console.print(Panel("Conversation history, token counts, file contents, code editor memory, and code editor files have been reset.", title="Reset", style="bold green"))
    display_token_usage()

def display_token_usage():
    from rich.table import Table
    from rich.panel import Panel
    from rich.box import ROUNDED

    table = Table(box=ROUNDED)
    table.add_column("Model", style="cyan")
    table.add_column("Input", style="magenta")
    table.add_column("Output", style="magenta")
    table.add_column("Total", style="green")
    table.add_column(f"% of Context ({MAX_CONTEXT_TOKENS:,})", style="yellow")
    table.add_column("Cost ($)", style="red")

    model_costs = {
        "Main Model": {"input": 3.00, "output": 15.00, "has_context": True},
        "Tool Checker": {"input": 3.00, "output": 15.00, "has_context": False},
        "Code Editor": {"input": 3.00, "output": 15.00, "has_context": True},
        "Code Execution": {"input": 3.00, "output": 15.00, "has_context": False}
    }

    total_input = 0
    total_output = 0
    total_cost = 0
    total_context_tokens = 0

    for model, tokens in [("Main Model", main_model_tokens),
                          ("Tool Checker", tool_checker_tokens),
                          ("Code Editor", code_editor_tokens),
                          ("Code Execution", code_execution_tokens)]:
        input_tokens = tokens['input']
        output_tokens = tokens['output']
        total_tokens = input_tokens + output_tokens

        total_input += input_tokens
        total_output += output_tokens

        input_cost = (input_tokens / 1_000_000) * model_costs[model]["input"]
        output_cost = (output_tokens / 1_000_000) * model_costs[model]["output"]
        model_cost = input_cost + output_cost
        total_cost += model_cost

        if model_costs[model]["has_context"]:
            total_context_tokens += total_tokens
            percentage = (total_tokens / MAX_CONTEXT_TOKENS) * 100
        else:
            percentage = 0

        table.add_row(
            model,
            f"{input_tokens:,}",
            f"{output_tokens:,}",
            f"{total_tokens:,}",
            f"{percentage:.2f}%" if model_costs[model]["has_context"] else "Doesn't save context",
            f"${model_cost:.3f}"
        )

    grand_total = total_input + total_output
    total_percentage = (total_context_tokens / MAX_CONTEXT_TOKENS) * 100

    table.add_row(
        "Total",
        f"{total_input:,}",
        f"{total_output:,}",
        f"{grand_total:,}",
        "",  # Empty string for the "% of Context" column
        f"${total_cost:.3f}",
        style="bold"
    )

    console.print(table)



async def main():
    global automode, conversation_history
    console.print(Panel("Welcome to the Netmiko AI Chat with Multi-Agent Support!", title="Welcome", style="bold green"))
    console.print("Type 'exit' to end the conversation.")
    console.print("Type 'image' to include an image in your message.")
    console.print("Type 'automode [number]' to enter Autonomous mode with a specific number of iterations.")
    console.print("Type 'reset' to clear the conversation history.")
    console.print("Type 'save chat' to save the conversation to a Markdown file.")
    console.print("While in automode, press Ctrl+C at any time to exit the automode to return to regular chat.")

    while True:
        user_input = await get_user_input()

        if user_input.lower() == 'exit':
            console.print(Panel("Thank you for chatting. Goodbye!", title_align="left", title="Goodbye", style="bold green"))
            break

        if user_input.lower() == 'reset':
            reset_conversation()
            continue

        if user_input.lower() == 'save chat':
            filename = save_chat()
            console.print(Panel(f"Chat saved to {filename}", title="Chat Saved", style="bold green"))
            continue

        if user_input.lower() == 'image':
            image_path = (await get_user_input("Drag and drop your image here, then press enter: ")).strip().replace("'", "")

            if os.path.isfile(image_path):
                user_input = await get_user_input("You (prompt for image): ")
                response, _ = await chat_with_claude(user_input, image_path)
            else:
                console.print(Panel("Invalid image path. Please try again.", title="Error", style="bold red"))
                continue
        elif user_input.lower().startswith('automode'):
            try:
                parts = user_input.split()
                if len(parts) > 1 and parts[1].isdigit():
                    max_iterations = int(parts[1])
                else:
                    max_iterations = MAX_CONTINUATION_ITERATIONS

                console.print(Panel("Warning: Automode will execute Netmiko scripts automatically. Ensure all scripts are reviewed for potential network impact before proceeding.", style="bold yellow"))
                user_confirmation = await get_user_input("Type 'CONFIRM' to proceed with automode: ")
                if user_confirmation.upper() != 'CONFIRM':
                    console.print(Panel("Automode cancelled.", style="bold red"))
                    continue

                automode = True
                console.print(Panel(f"Entering automode with {max_iterations} iterations. Please provide the goal of the automode.", title_align="left", title="Automode", style="bold yellow"))
                console.print(Panel("Press Ctrl+C at any time to exit the automode loop.", style="bold yellow"))
                user_input = await get_user_input()

                iteration_count = 0
                try:
                    while automode and iteration_count < max_iterations:
                        response, exit_continuation = await chat_with_claude(user_input, current_iteration=iteration_count+1, max_iterations=max_iterations)

                        if exit_continuation or CONTINUATION_EXIT_PHRASE in response:
                            console.print(Panel("Automode completed.", title_align="left", title="Automode", style="green"))
                            automode = False
                        else:
                            console.print(Panel(f"Continuation iteration {iteration_count + 1} completed. Press Ctrl+C to exit automode. ", title_align="left", title="Automode", style="yellow"))
                            user_input = "Continue with the next step. Or STOP by saying 'AUTOMODE_COMPLETE' if you think you've achieved the results established in the original request."
                        iteration_count += 1

                        if iteration_count >= max_iterations:
                            console.print(Panel("Max iterations reached. Exiting automode.", title_align="left", title="Automode", style="bold red"))
                            automode = False
                except KeyboardInterrupt:
                    console.print(Panel("\nAutomode interrupted by user. Exiting automode.", title_align="left", title="Automode", style="bold red"))
                    automode = False
                    if conversation_history and conversation_history[-1]["role"] == "user":
                        conversation_history.append({"role": "assistant", "content": "Automode interrupted. How can I assist you further?"})
            except KeyboardInterrupt:
                console.print(Panel("\nAutomode interrupted by user. Exiting automode.", title_align="left", title="Automode", style="bold red"))
                automode = False
                if conversation_history and conversation_history[-1]["role"] == "user":
                    conversation_history.append({"role": "assistant", "content": "Automode interrupted. How can I assist you further?"})

            console.print(Panel("Exited automode. Returning to regular chat.", style="green"))
        else:
            response, _ = await chat_with_claude(user_input)

if __name__ == "__main__":
    asyncio.run(main())


