import os
import openai
from dotenv import find_dotenv, load_dotenv
import time
import logging
import requests
import json
import streamlit as st
from datetime import datetime

load_dotenv()

client = openai.OpenAI()
model = "gpt-3.5-turbo-16k"

news_api_key = ${{secrets.NEWS_API_KEY}}


def get_news(topic):
    url = (
        f"https://newsapi.org/v2/everything?q={topic}&apiKey={news_api_key}&pageSize=5"
    )

    try:
        response = requests.get(url)
        if response.status_code == 200:
            news = json.dumps(response.json(), indent=4)
            news_json = json.loads(news)
            data = news_json

            #access all the fields == loop through
            status = data["status"]
            total_results = data["totalResults"]
            articles = data["articles"]

            final_news = []
            #loop through articles
            for article in articles:
                source_name = article["source"]["name"]
                author = article["author"]
                title = article["title"]
                description = article["description"]
                url = article["url"]
                published_at = article["publishedAt"]
                content = article["content"]
                title_description = f"""Title: {title}, Author: {author}, Source: {source_name}, 
                 description: {description}  URL: {url}"""
                final_news.append(title_description)
            return final_news

        else:
            return []

    except requests.exceptions.RequestException as e:
        print("Error occurred during API Rquest:", e)

class AssistantManager:
    thread_id = None
    assistant_id = None

    def __init__(self, model: str = model) -> None:
        self.client = client
        self.model = model
        self.assistant = None
        self.thread = None
        self.run = None
        self.summary = None

        if AssistantManager.assistant_id:
            self.assistant = self.client.beta.assistants.retrieve(
                AssistantManager.assistant_id
            )
        if AssistantManager.thread_id:
            self.thread = self.client.beta.threads.retrieve(AssistantManager.thread_id)

    def create_assistant(self, name, instructions, tools):
        if not self.assistant:
            assistant_obj = self.client.beta.assistants.create(
                name=name, instructions=instructions, tools=tools, model=self.model
            )
            AssistantManager.assistant_id = assistant_obj.id
            self.assistant = assistant_obj
            print(f"AssisID: {self.assistant.id}")
    
    def create_thread(self):
        if not self.thread:
            thread_obj = self.client.beta.threads.create()
            AssistantManager.thread_id = thread_obj.id
            self.thread = thread_obj
            print(f"ThreadID: {self.thread.id}")

    def add_message_to_thread(self, role, content):
        if self.thread:
            self.client.beta.threads.messages.create(
                thread_id=self.thread.id,
                role=role,
                content=content,
            )
    def run_assistant(self, instructions):
        if self.thread and self.assistant:
            self.run = self.client.beta.threads.runs.create(
                thread_id=self.thread.id,
                assistant_id=self.assistant.id,
                instructions=instructions,
            )
    def process_messages(self):
        if self.thread:
            messages = self.client.beta.threads.messages.list(thread_id=self.thread.id)
            summary = []
            # just get the last message of the thread
            last_message = messages.data[0]
            role = last_message.role
            response = last_message.content[0].text.value
            print(f"SUMMARY: {role.capitalize()}: ==> {response}")
            summary.append(response)
            #try changing to just self.summary = summary!!!
            self.summary = "\n".join(summary) 

            # loop through all messages in this thread
            # for msg in messages.data:
            #     role = msg.role
            #     content = msg.content[0].text.value
            #     print(f"SUMMARY:: {role.capitalize()}: {content}")

    # for streamlit
    def get_summary(self):
        return self.summary

    def run_steps(self):
        run_steps = self.client.beta.threads.runs.steps.list(
            thread_id=self.thread.id, run_id=self.run.id
        )
        print(f"Run-Steps: {run_steps}")
        return run_steps.data

    def wait_for_completion(self):
        if self.thread and self.run:
            while True:
                time.sleep(5)
                run_status = self.client.beta.threads.runs.retrieve(
                    thread_id=self.thread.id,
                    run_id=self.run.id,
                )

                print(f"RUN STATUS: {run_status.model_dump_json(indent=4)}")

                if run_status.status == "completed":
                    self.process_messages()
                    break
                elif run_status.status == "requires_action":
                    print("Function calling now....")
                    self.call_required_functions(
                        run_status.required_action.submit_tool_outputs.model_dump()
                    )
                else:
                    print("Waiting for the Assistant to process...")

    
    def call_required_functions(self, required_actions):
        if not self.run:
            return

        tool_outputs = []

        for action in required_actions["tool_calls"]:
            func_name = action["function"]["name"]
            arguments = json.loads(action["function"]["arguments"])

            if func_name == "get_news":
                output = get_news(topic=arguments["topic"])
                print(f"STUFF ===> {output}")
                final_str = ""
                for item in output:
                    final_str += "".join(item)

                tool_outputs.append({"tool_call_id": action["id"], "output": final_str})
            else:
                raise ValueError(f"Unknown function: {func_name}")

        print("Submitting outputs back to the Assistant...")

        self.client.beta.threads.runs.submit_tool_outputs(
            thread_id=self.thread.id,
            run_id=self.run.id,
            tool_outputs=tool_outputs,
        )

def main():
    manager = AssistantManager()

    # Streamlit interface
    st.title("News Summarizer")

    # Form for user input
    with st.form(key="user_input_form"):
        instructions = st.text_area("Enter topic:")
        submit_button = st.form_submit_button(label="Run Assistant")
    # Handling the button click
    if submit_button:
        # Create the assistant and thread if they don't exist
        manager.create_assistant(
            name="News Summarizer",
            instructions="You are a personal article summarizer Assistant who knows how to take a list of article's titles and descriptions and then write a short summary of all the news articles",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_news",
                        "description": "Get the list of articles/news for the given topic",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "topic": {
                                    "type": "string",
                                    "description": "The topic for the news, e.g. bitcoin",
                                }
                            },
                            "required": ["topic"],
                        },
                    },
                }
            ],
        )
        manager.create_thread()

        # Add the message and run the assistant
        manager.add_message_to_thread(
            role="user", content=f"summarize the news on this topic {instructions}?"
        )
        manager.run_assistant(instructions="Summarize the news")

        # Wait for completion and process messages
        manager.wait_for_completion()

        summary = (
            manager.get_summary()
        )  # Implement get_summary() in your AssistantManager
        st.write(summary)

        st.text("Run Steps:")
        st.code(manager.run_steps(), line_numbers=True)

if __name__ == "__main__":
    main()
