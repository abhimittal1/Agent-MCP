from dotenv import load_dotenv
from openai import OpenAI
import json
import os
import requests
from pypdf import PdfReader
import gradio as gr


load_dotenv(override=True)

def push(text):
    response = requests.post(
        "https://api.pushover.net/1/messages.json",
        data={
            "token": os.getenv("PUSHOVER_TOKEN"),
            "user": os.getenv("PUSHOVER_USER"),
            "message": text,
        }
    )
    print(f"Push status: {response.status_code} | {response.json()}", flush=True)


def record_user_details(email, name="Name not provided", notes="not provided"):
    push(f"Recording interest from {name} with email {email} and notes {notes}")
    return {"recorded": "ok"}

def record_unknown_question(question):
    push(f"Recording unknown question: {question}")
    return {"recorded": "ok"}

record_user_details_json = {
    "name": "record_user_details",
    "description": "Use this tool to record that a user is interested in being in touch and provided an email address",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": "The email address of this user"
            },
            "name": {
                "type": "string",
                "description": "The user's name, if they provided it"
            },
            "notes": {
                "type": "string",
                "description": "Any additional information about the conversation that's worth recording to give context"
            }
        },
        "required": ["email"],
        "additionalProperties": False
    }
}

record_unknown_question_json = {
    "name": "record_unknown_question",
    "description": "Always use this tool to record any question that couldn't be answered as you didn't know the answer",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question that couldn't be answered"
            },
        },
        "required": ["question"],
        "additionalProperties": False
    }
}

tools = [{"type": "function", "function": record_user_details_json},
         {"type": "function", "function": record_unknown_question_json}]


class Me:

    def __init__(self):
        self.openai = OpenAI()
        self.name = "Abhishek Mittal"
        reader = PdfReader("me/Abhishek_Mittal_Resume.pdf")
        self.linkedin = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                self.linkedin += text
        with open("me/Abhishek.txt", "r", encoding="utf-8") as f:
            self.summary = f.read()

    def handle_tool_call(self, tool_calls):
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            print(f"Tool called: {tool_name} with arguments {arguments}", flush=True)
            tool = globals().get(tool_name)
            result = tool(**arguments) if tool else {}
            results.append({"role": "tool", "content": json.dumps(result), "tool_call_id": tool_call.id})
        return results

    def system_prompt(self):
        prompt = f"""You are a professional AI representative acting as {self.name}. Your role is to engage with visitors, answer questions about {self.name}'s background, experience, and skills, and identify potential professional connections.

## Your Identity
You are {self.name}. Respond in first person, maintaining a confident, professional, and approachable tone at all times.

## Knowledge Base
You have access to the following information about {self.name}. Only answer questions based on this information — do not fabricate or infer details not explicitly present.

### Resume
{self.linkedin}

### Personal Summary
{self.summary}

## Tool Usage Rules (STRICT — NO EXCEPTIONS)
- If ANY question cannot be answered directly from the Resume or Personal Summary above, you MUST call `record_unknown_question` BEFORE responding. No exceptions.
- If the user shares an email address in ANY message for ANY reason, you MUST immediately call `record_user_details` with that email. No exceptions.
- These tools are mandatory actions, not suggestions.

## Behavioral Guidelines
- Speak in first person as {self.name} — never break character
- Be concise, professional, and helpful in all responses
- If asked something you cannot answer, be transparent: say you're not sure, then use `record_unknown_question` to log it
- If a visitor expresses interest in connecting, collaborating, or learning more, ask for their email and use `record_user_details` to capture it
- Do not speculate, exaggerate, or provide information not supported by the resume or summary
- If the user is engaging in discussion, steer them towards getting in touch via email or connecting on LinkedIn
- Keep responses focused and relevant to professional topics
"""
        return prompt

    def chat(self, message, history):
        messages = [{"role": "system", "content": self.system_prompt()}] + history + [{"role": "user", "content": message}]
        done = False
        while not done:
            response = self.openai.chat.completions.create(model="gpt-4o", messages=messages, tools=tools)
            if response.choices[0].finish_reason == "tool_calls":
                assistant_message = response.choices[0].message
                tool_calls = assistant_message.tool_calls
                results = self.handle_tool_call(tool_calls)
                messages.append(assistant_message)
                messages.extend(results)
            else:
                done = True
        return response.choices[0].message.content


if __name__ == "__main__":
    me = Me()
    gr.ChatInterface(me.chat, type="messages").launch()