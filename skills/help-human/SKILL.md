---
name: help-human
description: Help the owner figure out what they actually want before any work starts. Use when the owner says "help human" or /help-human, or brings a fuzzy task, idea or goal and wants to think it through. Ends in a clear goal and a fairly detailed plan, built by asking questions one at a time.
---

# Help Human

The aim is clarity, not execution. The owner often starts with a rough idea. Your job is to help them see what they want, then turn that into a plan they agree with. Don't do the task itself in this skill.

## Steps

1. **Gather context quietly first.** Read whatever you can find: the related issue, workstream notes, repo, `people/`, earlier notes. Don't ask anything the files already answer.

2. **Play it back.** In 2–4 sentences say how you understand the task: the goal, why it matters, what done looks like. Name your assumptions so they can be corrected.

3. **Ask questions one at a time.** Start with the question whose answer changes the plan the most.
   - Every question comes with 2–4 concrete options plus your recommendation, so the owner picks rather than writes an essay. Use AskUserQuestion when the options are clear.
   - After each answer, briefly say what it changes, then ask the next question.
   - Cover what matters: the goal, scope, constraints, what done looks like, and risks they may not have thought of.
   - If an answer shows they don't know yet, say so and offer a way to find out (a small experiment, research, asking someone). Don't press.
   - Stop when more answers wouldn't change the plan. That's usually 3–7 questions.

4. **Write the plan.** Concrete enough that each step can be started, and say who does what. Keep it as short as the task allows.

5. **Confirm and save.** Adjust the plan until they say yes. Then offer to save it: as a GitHub issue (`scripts/task.sh new`), in the workstream's `notes.md`, or nowhere if it was just thinking out loud.

## Tone

- Short messages. One question per message, not a questionnaire.
- Disagree when something looks off ("this goal conflicts with X, are you sure?").
- Don't invent requirements. If something doesn't matter, don't ask about it.
