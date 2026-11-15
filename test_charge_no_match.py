import agent

messages = [
    "I see an unknown charge on my card",
    "4321 on 3 March 2026",
    "Asha Rao, 9800000001, asha@mail.com",
]

for message in messages:
    agent.customer_messages += " " + message
    reply = agent.chat.send_message(message)
    print("CUSTOMER:", message)
    print("AGENT:", reply.text)

print("Tools called:", agent.tool_calls)

if "get_plans" in agent.tool_calls:
    print("PASS: get_plans was called")
else:
    print("FAIL: get_plans was not called")
if "create_ticket" in agent.tool_calls:
    print("FAIL: a ticket was created before asking where the charge was seen")
else:
    print("PASS: no ticket was created")
print("CHECK BY HAND: the last reply should say nothing matches and ask where they saw the charge.")
