import os
import asyncio
import sys
import subprocess
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from typing import Dict, Any
import uuid
from models import update_token_usage

from utils import read_file, read_multiple_files, list_files
from models import client, CODEEXECUTIONMODEL

console = Console()

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

async def execute_code(code: str, timeout: int = 10) -> Dict[str, Any]:
    process_id = str(uuid.uuid4())
    
    # Display the code before writing it to a file
    syntax = Syntax(code, "python", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title="Code to be executed", expand=False))
    
    # Write the code to a temporary file
    with open(f"{process_id}.py", "w") as f:
        f.write(code)
    
    console.print(f"Code written to file: {process_id}.py", style="bold green")
    
    # Prepare the command to run the code
    if sys.platform == "win32":
        command = f'conda run -n netmikoai python "{process_id}.py"'
    else:
        command = f'conda run -n netmikoai python {process_id}.py'
    
    # Create a process to run the command
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        shell=True
    )
    
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
    
    return {
        "stdout": stdout,
        "stderr": stderr,
        "return_code": return_code
    }

def stop_process(process_id: str) -> str:
    # Implement the stop_process logic here
    pass

async def tavily_search(query: str) -> Dict[str, Any]:
    # Implement the Tavily search functionality here
    # For now, we'll return a placeholder message
    return {"result": f"Tavily search results for query: {query}"}

async def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = None
        is_error = False

        if tool_name == "execute_code":
            execution_result = await execute_code(tool_input["code"])
            analysis_task = asyncio.create_task(send_to_ai_for_executing(tool_input["code"], str(execution_result)))
            analysis = await analysis_task
            result = execution_result
        elif tool_name == "stop_process":
            result = stop_process(tool_input["process_id"])
        elif tool_name == "read_file":
            result = read_file(tool_input["path"])
        elif tool_name == "read_multiple_files":
            result = read_multiple_files(tool_input["paths"])
        elif tool_name == "list_files":
            result = list_files(tool_input.get("path", "."))
        elif tool_name == "tavily_search":
            result = await tavily_search(tool_input["query"])
        else:
            is_error = True
            result = f"Unknown tool: {tool_name}"

        return {
            "content": result,
            "is_error": is_error
        }
    except KeyError as e:
        return {
            "content": f"Error: Missing required parameter {str(e)} for tool {tool_name}",
            "is_error": True
        }
    except Exception as e:
        return {
            "content": f"Error executing tool {tool_name}: {str(e)}",
            "is_error": True
        }

async def send_to_ai_for_executing(code, execution_result):
    try:
        response = client.messages.create(
            model=CODEEXECUTIONMODEL,
            max_tokens=2000,
            system="",
            messages=[
                {"role": "user", "content": f"Analyze this Netmiko script execution from the 'code_execution_env' virtual environment:\n\nScript:\n{code}\n\nExecution Result:\n{execution_result}"}
            ]
        )
        update_token_usage("code_execution", response.usage.input_tokens, response.usage.output_tokens)
        return response
    except Exception as e:
        return f"Error sending to AI for executing: {str(e)}"