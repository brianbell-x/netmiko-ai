import os
from dotenv import load_dotenv
import asyncio
from anthropic import Anthropic
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style

# Import other modules (assuming they've been created)
from models import MAINMODEL, TOOLCHECKERMODEL, CODEEDITORMODEL, CODEEXECUTIONMODEL
from tools import tools, execute_tool
from utils import (encode_image_to_base64, parse_goals, execute_goals, save_chat,
                   display_token_usage, read_file, read_multiple_files, list_files, reset_conversation)
from config import (load_prompt, BASE_SYSTEM_PROMPT, AUTOMODE_SYSTEM_PROMPT,
                    CONTINUATION_EXIT_PHRASE, MAX_CONTINUATION_ITERATIONS, MAX_CONTEXT_TOKENS,
                    update_system_prompt)

# Load environment variables
load_dotenv()

# Initialize clients
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
if not anthropic_api_key:
    raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
client = Anthropic(api_key=anthropic_api_key)

console = Console()

# Global variables
conversation_history = []
file_contents = {}
automode = False
running_processes = {}

async def get_user_input(prompt="You: "):
    style = Style.from_dict({'prompt': 'cyan bold'})
    session = PromptSession(style=style)
    return await session.prompt_async(prompt, multiline=False)

def update_system_prompt(current_iteration=None, max_iterations=None):
    global file_contents
    chain_of_thought_prompt = load_prompt('chain_of_thought_prompt.txt')
    
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

async def chat_with_claude(user_input, image_path=None, current_iteration=None, max_iterations=None):
    global conversation_history, automode

    current_conversation = []

    if image_path:
        console.print(Panel(f"Processing image at path: {image_path}", title="Image Processing", style="yellow"))
        image_base64 = encode_image_to_base64(image_path)
        if image_base64.startswith("Error"):
            console.print(Panel(f"Error encoding image: {image_base64}", title="Error", style="bold red"))
            return "I'm sorry, there was an error processing the image. Please try again.", False
        image_message = {
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64}},
                {"type": "text", "text": f"User input for image: {user_input}"}
            ]
        }
        current_conversation.append(image_message)
    else:
        current_conversation.append({"role": "user", "content": user_input})

    # Filter conversation history to maintain context
    filtered_conversation_history = [
        message for message in conversation_history
        if not (isinstance(message['content'], list) and
                any(content.get('type') == 'tool_result' and
                    any(keyword in content.get('output', '') for keyword in [
                        "File contents updated in system prompt",
                        "File created and added to system prompt",
                        "has been read and stored in the system prompt"
                    ]) for content in message['content']))
    ]

    messages = filtered_conversation_history + current_conversation

    try:
        response = client.messages.create(
            model=MAINMODEL,
            max_tokens=8000,
            system=update_system_prompt(current_iteration, max_iterations),
            extra_headers={"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"},
            messages=messages,
            tools=tools,
            tool_choice={"type": "auto"}
        )
        from models import update_token_usage
        update_token_usage("main", response.usage.input_tokens, response.usage.output_tokens)
    except Exception as e:
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

    console.print(Panel(Markdown(assistant_response), title="Claude's Response", border_style="blue"))

    for tool_use in tool_uses:
        tool_result = await execute_tool(tool_use.name, tool_use.input)
        console.print(Panel(tool_result["content"], title="Tool Result", style="green" if not tool_result["is_error"] else "bold red"))
        current_conversation.extend([
            {"role": "assistant", "content": [{"type": "tool_use", "id": tool_use.id, "name": tool_use.name, "input": tool_use.input}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": tool_result["content"], "is_error": tool_result["is_error"]}]}
        ])

        try:
            tool_response = client.messages.create(
                model=TOOLCHECKERMODEL,
                max_tokens=8000,
                system=update_system_prompt(current_iteration, max_iterations),
                extra_headers={"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"},
                messages=filtered_conversation_history + current_conversation,
                tools=tools,
                tool_choice={"type": "auto"}
            )
            update_token_usage("tool_checker", tool_response.usage.input_tokens, tool_response.usage.output_tokens)
            tool_checker_response = "".join(block.text for block in tool_response.content if block.type == "text")
            console.print(Panel(Markdown(tool_checker_response), title="Claude's Response to Tool Result", border_style="blue"))
            assistant_response += "\n\n" + tool_checker_response
        except Exception as e:
            error_message = f"Error in tool response: {str(e)}"
            console.print(Panel(error_message, title="Error", style="bold red"))
            assistant_response += f"\n\n{error_message}"

    conversation_history = messages + [{"role": "assistant", "content": assistant_response}]
    display_token_usage()
    return assistant_response, exit_continuation

async def main():
    global automode
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
            console.print(Panel("Thank you for chatting. Goodbye!", title="Goodbye", style="bold green"))
            break

        if user_input.lower() == 'reset':
            conversation_history = reset_conversation()
            console.print(Panel("Conversation history has been reset.", style="bold green"))
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
                max_iterations = int(user_input.split()[1]) if len(user_input.split()) > 1 else MAX_CONTINUATION_ITERATIONS
                console.print(Panel("Warning: Automode will execute Netmiko scripts automatically. Ensure all scripts are reviewed for potential network impact before proceeding.", style="bold yellow"))
                if (await get_user_input("Type 'CONFIRM' to proceed with automode: ")).upper() != 'CONFIRM':
                    console.print(Panel("Automode cancelled.", style="bold red"))
                    continue
                
                automode = True
                console.print(Panel(f"Entering automode with {max_iterations} iterations. Please provide the goal of the automode.", title="Automode", style="bold yellow"))
                console.print(Panel("Press Ctrl+C at any time to exit the automode loop.", style="bold yellow"))
                user_input = await get_user_input()

                for iteration_count in range(max_iterations):
                    try:
                        response, exit_continuation = await chat_with_claude(user_input, current_iteration=iteration_count+1, max_iterations=max_iterations)
                        if exit_continuation or CONTINUATION_EXIT_PHRASE in response:
                            console.print(Panel("Automode completed.", title="Automode", style="green"))
                            break
                        console.print(Panel(f"Continuation iteration {iteration_count + 1} completed. Press Ctrl+C to exit automode.", title="Automode", style="yellow"))
                        user_input = "Continue with the next step. Or STOP by saying 'AUTOMODE_COMPLETE' if you think you've achieved the results established in the original request."
                    except KeyboardInterrupt:
                        console.print(Panel("\nAutomode interrupted by user. Exiting automode.", title="Automode", style="bold red"))
                        break
                else:
                    console.print(Panel("Max iterations reached. Exiting automode.", title="Automode", style="bold red"))
            except KeyboardInterrupt:
                console.print(Panel("\nAutomode interrupted by user. Exiting automode.", title="Automode", style="bold red"))
            
            automode = False
            console.print(Panel("Exited automode. Returning to regular chat.", style="green"))
        else:
            await chat_with_claude(user_input)

if __name__ == "__main__":
    asyncio.run(main())