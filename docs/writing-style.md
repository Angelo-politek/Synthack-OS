# Writing style

For every text in the project: site, docs, READMEs, UI labels, issues, pull requests.

## Rules

- Short sentences. One fact per sentence.
- Lists and tables before paragraphs. Steps are numbered.
- Instructions start with the verb: *Download*, *Drop*, *Hold FUNC*, *Turn knob C*.
- Concrete over vague: OS 1.42, keys 13–16, 30–60 s, page 2 of the REVERB tab.
- Second person, present tense, American English.
- Headings: 1–4 words, nouns or verbs. No questions, except **Why SyntHack**.
- Say it once. No intro, no recap, no closing line.

## Never

- Hype: *powerful, seamless, effortless, robust, unleash, elevate, empower, game-changer, cutting-edge, next-level*.
- Filler: *simply, just, easily, basically, actually, in order to, it's worth noting, whether you're …*.
- Section openers like *In this section we will …* and sign-offs like *Happy hacking!*.
- Rhetorical questions, exclamation marks, emoji in body text.
- Claims nobody measured. If it isn't tested, say so.

## Look

The cyberpunk/coding flavor lives in the chrome, not in the sentences:

- section indices `01`, `02`;
- `//` kickers above headings;
- monospace for keys, values, file names: `FUNC` + `15`, `12.5ms`, `patch.json`;
- status tags: `[ok]`, `[!]`, `[wip]`.

One flavor element per block at most; `[!]` notes are content, not flavor, and can repeat. No hacker slang, no fake
terminal prompts.

## Example

Bad:

> Unleash the full potential of your Syntakt! With our powerful Performance FX mod, you can easily add stunning
> repeat effects to your live sets.

Good:

> **Performance FX**
> Repeat, reverse and half speed on keys 13–16.
> 1. Press `FUNC` + `15` to select Mod A.
> 2. Hold a key 13–16. The effect plays.
> 3. Release. Playback resumes in time.
