# EveryLot Cincinnati Bot

A bot that posts images of every property lot in Cincinnati to Bluesky. 

I'll save you from having to read a mile long AI-generated README. You weren't going to read it anyway. If you care, look at README.md from the source fork: [everylotbot-chicago](https://github.com/MisterClean/everylotbot-chicago). This ain't rocket science, you'll figure it out.

[cincinnati_data.md](cincinnati_data.md) describes how the source data was derived. Its a manual process as there were no good APIs for Cincinnati. 

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file from the example & configure it:
```bash
cp .env.example .env
```
### Running the Bot

Basic usage:
```bash
python3 -m everylot.bot --dry-run --verbose --id 1000 
```

### Running Automatically

To run the bot automatically, set up a cron job. For example, to post every hour:

```bash
0 * * * * cd /path/to/everylotbot-chicago && python -m everylot.bot >> bot.log 2>&1
```

### License

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
