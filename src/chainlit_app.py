import os
import uuid
import asyncio
import chainlit as cl
from dotenv import load_dotenv

load_dotenv()

from agent import Context, write_memory, get_memory
from main import get_latest_system_prompt
from model_pool import ModelPool, AGENT_MODELS
from langchain.agents import create_agent

pool = ModelPool(AGENT_MODELS)

with open(get_latest_system_prompt()) as f:
    SYSTEM_PROMPT = f.read()

def make_agent(model: str):
    """Creates the LangChain agent using the specified model."""
    llm = pool.get_llm(model)
    return create_agent(
        model=llm,
        system_prompt=SYSTEM_PROMPT,
        tools=[write_memory, get_memory],
        context_schema=Context,
    )

@cl.on_chat_start
async def on_chat_start():
    """Initializes a new chat session."""
    agent = make_agent(pool.current)
    
    cl.user_session.set("agent", agent)
    cl.user_session.set("history", [])
    
    user_id = str(uuid.uuid4())
    cl.user_session.set("context", Context(user_id=user_id))
    
    greeting = "Hello! I'm here to listen. How are you feeling today?"
    await cl.Message(content=greeting, author="Therapist").send()

@cl.on_message
async def on_message(message: cl.Message):
    """Handles incoming user messages and agent responses."""
    agent = cl.user_session.get("agent")
    history = cl.user_session.get("history")
    ctx = cl.user_session.get("context")
    
    history.append(message.content)
    
    msg = cl.Message(content="", author="Therapist")
    await msg.send()
    
    try:
        res = await asyncio.to_thread(
            agent.invoke,
            {'messages': history},
            context=ctx
        )
        
        if res and 'messages' in res:
            new_history = res['messages']
            cl.user_session.set("history", new_history)
            
            reply = new_history[-1].content
            
            msg.content = reply
            await msg.update()
        else:
            msg.content = "An error occurred: the agent returned an empty response."
            await msg.update()
            
    except Exception as e:
        msg.content = f"An unexpected error occurred: {str(e)}"
        await msg.update()
