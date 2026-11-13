---
name: tag-compliance
description: Check an Azure resource group for resources that are missing an owner tag.
---
Use `tag.inspect` when the user wants to know which Azure resources lack an owner tag.
Pass the request in plain words in `request`. If the agent asks which subscription or resource group,
ask the user and send their reply in `answer`. The agent only reads; it never changes tags.
