"""Human-readable meanings for Architect action types.

Keyed on the `__type` values Architect actually emits in a flow's published
configuration (`PlayAudioAction`, `TransferPureMatchAction`, ...). The table was
built by inventorying every type present across a real org, but Architect grows
new ones with each release: anything missing is still documented from its raw
configuration and is listed as unrecognised in the technical document, so a gap
is always visible rather than silently swallowed.
"""

from __future__ import annotations

import re

# __type -> (technical label, what it means in business terms, category)
ACTIONS: dict[str, tuple[str, str, str]] = {
    # --- Containers -------------------------------------------------------
    "Task": ("Task", "A named stage of the call.", "container"),
    "Menu": ("Menu", "A set of keypad options offered to the caller.", "container"),
    "State": ("State", "A named state of the flow.", "container"),

    # --- Audio ------------------------------------------------------------
    "PlayAudioAction": ("Play Audio", "Plays a message to the caller.", "audio"),
    "PlayAudioOnSilenceAction": ("Play Audio On Silence", "Plays a message if the caller says nothing.", "audio"),
    "PlayEstimatedWaitTimeAction": ("Play Estimated Wait Time", "Tells the caller how long they are likely to wait.", "audio"),
    "PlayPositionInQueueAction": ("Play Position In Queue", "Tells the caller their place in the queue.", "audio"),
    "HoldMusicAction": ("Hold Music", "Plays hold music or comfort audio.", "audio"),
    "FlushAudioAction": ("Flush Audio", "Stops any audio currently playing.", "audio"),
    "CommunicateAction": ("Communicate", "Speaks a message to the caller.", "audio"),

    # --- Caller input -----------------------------------------------------
    "CollectInputAction": ("Collect Input", "Asks the caller to key in information, such as an account or case number.", "input"),
    "GetResponseAction": ("Get Response", "Asks a question and captures the reply.", "input"),
    "AskForIntentAction": ("Ask For Intent", "Asks the caller what they need and interprets the answer.", "input"),
    "AskForSlotAction": ("Ask For Slot", "Asks the caller for a specific piece of information.", "input"),
    "AskForBooleanAction": ("Ask For Yes or No", "Asks the caller a yes/no question.", "input"),
    "DetectSilenceAction": ("Detect Silence", "Reacts when the caller does not respond.", "input"),
    "PreviousMenuAction": ("Previous Menu", "Takes the caller back to the previous menu.", "input"),
    "RepeatMenuAction": ("Repeat Menu", "Repeats the menu options.", "input"),

    # --- Routing / transfer ------------------------------------------------
    "TransferPureMatchAction": ("Transfer to ACD", "Puts the call in a queue to be answered by an agent.", "routing"),
    "TransferAcdAction": ("Transfer to ACD", "Puts the call in a queue to be answered by an agent.", "routing"),
    "TransferUserAction": ("Transfer to User", "Sends the call to a named person.", "routing"),
    "TransferExternalAction": ("Transfer to Number", "Sends the call to an external phone number.", "routing"),
    "TransferGroupAction": ("Transfer to Group", "Sends the call to a group of people.", "routing"),
    "TransferVoicemailAction": ("Transfer to Voicemail", "Sends the caller to voicemail to leave a message.", "routing"),
    "TransferFlowAction": ("Transfer to Flow", "Hands the call to another call flow.", "routing"),
    "TransferFlowSecureAction": ("Transfer to Secure Flow", "Hands the call to a secure call flow for sensitive steps.", "routing"),
    "TransferAcdVoicemailAction": ("Transfer to Queue Voicemail", "Sends the caller to a queue's voicemail.", "routing"),
    "DequeueAction": ("Dequeue", "Takes the call back out of the queue.", "routing"),
    "ReturnToAgentAction": ("Return to Agent", "Hands the interaction back to the agent.", "routing"),

    # --- Flow control ------------------------------------------------------
    "DecisionAction": ("Decision", "Checks a condition and takes one of two paths.", "logic"),
    "SwitchAction": ("Switch", "Takes one of several paths depending on a value.", "logic"),
    "LoopAction": ("Loop", "Repeats a set of steps a number of times.", "logic"),
    "WhileLoopAction": ("While Loop", "Repeats a set of steps while a condition holds.", "logic"),
    "EachLoopAction": ("Each Loop", "Repeats a set of steps for every item in a list.", "logic"),
    "ExitLoopAction": ("Exit Loop", "Stops repeating and moves on.", "logic"),
    "NextLoopAction": ("Next Loop Iteration", "Skips to the next repetition.", "logic"),
    "TransferTaskAction": ("Jump to Task", "Continues at another stage of the call.", "logic"),
    "TaskAction": ("Task", "Runs another stage of the call.", "logic"),
    "TransferMenuAction": ("Jump to Menu", "Takes the caller to another menu.", "logic"),
    "MenuAction": ("Sub Menu", "Opens a further set of keypad options.", "logic"),
    "CallCommonModuleAction": ("Call Common Module", "Runs a shared, reusable piece of flow logic.", "logic"),
    "ChangeStateAction": ("Change State", "Moves the flow into a different state.", "logic"),
    "WaitAction": ("Wait", "Pauses for a period of time.", "logic"),
    "EvaluateScheduleAction": ("Evaluate Schedule", "Checks the call against an opening-hours schedule.", "logic"),
    "EvaluateScheduleGroupAction": ("Evaluate Schedule Group", "Decides whether the business is open, closed or on holiday.", "logic"),

    # --- Data ---------------------------------------------------------------
    "UpdateVariableAction": ("Update Data", "Sets or changes values used later in the flow.", "data"),
    "SetAttributesAction": ("Set Participant Data", "Attaches information to the call so agents and reports can see it.", "data"),
    "GetAttributesAction": ("Get Participant Data", "Reads information already attached to the call.", "data"),
    "DataAction": ("Call Data Action", "Calls an external system to look something up.", "data"),
    "DataTableLookupAction": ("Data Table Lookup", "Looks a value up in a configured data table.", "data"),
    "FindUserAction": ("Find User", "Looks up a person in the organisation.", "data"),
    "FindQueueAction": ("Find Queue", "Looks up a queue by name.", "data"),
    "FindGroupAction": ("Find Group", "Looks up a group by name.", "data"),
    "FindSkillAction": ("Find Skill", "Looks up an agent skill.", "data"),
    "FindLanguageSkillAction": ("Find Language Skill", "Looks up a language skill.", "data"),
    "FindSystemPromptAction": ("Find System Prompt", "Looks up a built-in prompt.", "data"),
    "FindUserPromptAction": ("Find User Prompt", "Looks up a recorded prompt.", "data"),
    "ExtractSecureDataAction": ("Extract Secure Data", "Reads sensitive data in a protected way.", "data"),
    "SetLocaleAction": ("Set Language", "Switches the language used for prompts.", "data"),
    "ScreenPopAction": ("Screen Pop", "Prepares the information shown on the agent's screen when they answer.", "data"),
    "SetWrapupCodeAction": ("Set Wrap-up Code", "Records a wrap-up code against the interaction.", "data"),
    "SetUUIDataAction": ("Set UUI Data", "Sets user-to-user information passed with the call.", "data"),
    "SetExternalTagAction": ("Set External Tag", "Tags the call with an external reference for reporting.", "data"),
    "SetIntentAction": ("Set Intent", "Records what the caller wants.", "data"),
    "GetSIPHeadersAction": ("Get SIP Headers", "Reads technical details supplied by the telephony carrier.", "data"),
    "GetRawSIPHeadersAction": ("Get Raw SIP Headers", "Reads the raw telephony signalling data.", "data"),
    "SetPostFlowAction": ("Set Post-Flow", "Arranges what happens after the call, such as a customer survey.", "data"),
    "TranscriptionAction": ("Transcription", "Turns call transcription on or off.", "data"),
    "AudioMonitoringAction": ("Audio Monitoring", "Turns audio monitoring on or off.", "data"),

    # --- Bots ----------------------------------------------------------------
    "CallBotFlowAction": ("Call Bot Flow", "Hands the conversation to an automated assistant.", "bot"),
    "CallBotAction": ("Call Bot", "Hands the conversation to an automated assistant.", "bot"),
    "CallDigitalBotFlowAction": ("Call Digital Bot Flow", "Hands the conversation to a digital bot flow.", "bot"),
    "CallDialogEngineBotAction": ("Call Dialog Engine Bot", "Hands the conversation to a Dialog Engine bot.", "bot"),
    "CallLexBotAction": ("Call Lex Bot", "Hands the conversation to an Amazon Lex bot.", "bot"),
    "CallLexV2BotAction": ("Call Lex V2 Bot", "Hands the conversation to an Amazon Lex V2 bot.", "bot"),
    "CallAudioConnectorAction": ("Call Audio Connector", "Streams the call to an external voice bot.", "bot"),
    "ExitBotAction": ("Exit Bot", "Ends the automated assistant.", "bot"),
    "SearchKnowledgeAction": ("Search Knowledge", "Looks for an answer in the knowledge base.", "bot"),

    # --- Terminal --------------------------------------------------------------
    "DisconnectAction": ("Disconnect", "Ends the call.", "terminal"),
    "EndTaskAction": ("End Task", "Ends this stage of the call.", "terminal"),
    "EndStateAction": ("End State", "Ends this state.", "terminal"),
    "EndWorkflowAction": ("End Workflow", "Ends the workflow.", "terminal"),
    "JumpToReusableTaskAction": ("Jump to Reusable Task", "Continues in a shared task.", "logic"),
}

# Variable declarations share the same __type namespace as actions.
VARIABLE_TYPES = {
    "StringVariable": "Text",
    "IntegerVariable": "Whole number",
    "DecimalVariable": "Decimal number",
    "BoolVariable": "Yes/No",
    "JsonVariable": "JSON",
    "QueueVariable": "Queue",
    "PhoneNumberVariable": "Phone number",
    "SkillVariable": "Skill",
    "UserVariable": "User",
    "GroupVariable": "Group",
    "DurationVariable": "Duration",
    "DateTimeVariable": "Date/time",
    "CurrencyVariable": "Currency",
    "PromptVariable": "Prompt",
    "AudioVariable": "Audio",
    "CommunicationVariable": "Communication",
    "WrapupCodeVariable": "Wrap-up code",
    "LanguageSkillVariable": "Language skill",
    "EmergencyGroupVariable": "Emergency group",
    "ScheduleVariable": "Schedule",
    "ScheduleGroupVariable": "Schedule group",
    "DataTableVariable": "Data table",
}

CONTAINER_TYPES = {"Task", "Menu", "State"}

TERMINAL_KINDS = {k for k, v in ACTIONS.items() if v[2] == "terminal"}
ROUTING_KINDS = {k for k, v in ACTIONS.items() if v[2] == "routing"}


def prettify(kind: str) -> str:
    """'TransferPureMatchAction' -> 'Transfer Pure Match', for unknown types."""
    name = re.sub(r"Action$", "", str(kind))
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", name).replace("_", " ")
    return re.sub(r"\s+", " ", spaced).strip().title() or str(kind)


def label_for(kind: str) -> str:
    entry = ACTIONS.get(kind)
    if entry:
        return entry[0]
    if kind in VARIABLE_TYPES:
        return VARIABLE_TYPES[kind]
    return prettify(kind)


def business_for(kind: str) -> str:
    entry = ACTIONS.get(kind)
    return entry[1] if entry else "Performs the '" + prettify(kind) + "' step."


def category_for(kind: str) -> str:
    entry = ACTIONS.get(kind)
    return entry[2] if entry else "other"


def is_known(kind: str) -> bool:
    return kind in ACTIONS or kind in VARIABLE_TYPES
