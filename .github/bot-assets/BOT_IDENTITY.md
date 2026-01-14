# AI Engineering Maintenance Bot Identity

This document defines the visual and textual identity of the **AI Engineering Maintenance Bot** (aieng-bot).

## Bot Name
**AI Engineering Maintenance Bot** (short: `aieng-bot`)

## Purpose
Automated maintenance bot for Vector Institute repositories that:
- Auto-merges Dependabot PRs when all checks pass
- Automatically fixes common issues in failing Dependabot PRs
- Maintains code quality and security standards

## Visual Identity

### Avatar Specifications
The bot should have a professional, technical avatar that represents:
- **Theme**: AI + Engineering + Maintenance
- **Style**: Modern, clean, geometric
- **Colors**: Vector Institute brand colors (if available), or:
  - Primary: Deep blue (#1E3A8A) - representing reliability and trust
  - Secondary: Green (#10B981) - representing automated fixes and success
  - Accent: Orange (#F59E0B) - representing active maintenance
- **Elements**: Consider incorporating:
  - A wrench or gear (maintenance)
  - A robot or AI symbol
  - Code brackets or technical elements
  - Vector Institute logo elements (if permitted)

### Avatar Design Concepts

#### Option 1: Minimalist Robot
A simple, geometric robot icon with:
- Circular head with friendly "eyes" (two dots or simple shapes)
- Wrench or tools as "arms" or accessories
- Clean lines, flat design
- Primary colors: blue and green

#### Option 2: Abstract Technical
An abstract representation combining:
- Overlapping geometric shapes suggesting AI/automation
- Subtle gear or mechanical elements
- Gradient from blue to green
- Modern, professional appearance

#### Option 3: Badge Style
A circular badge design with:
- "AI" or robot symbol in the center
- Wrench or tool crossed behind
- Border with subtle technical patterns
- Vector Institute affiliation indication

### Creating the Avatar
To create the avatar, you can:

1. **Use AI Image Generation** (recommended):
   - Tool: DALL-E, Midjourney, or Stable Diffusion
   - Prompt example: "Minimalist flat design robot icon for software maintenance bot, geometric shapes, blue and green colors, wrench symbol, professional tech company style, circular avatar, clean lines, white background"

2. **Use Design Tools**:
   - Figma, Adobe Illustrator, or Canva
   - Start with geometric shapes
   - Keep it simple and scalable
   - Export as PNG (512x512px minimum) or SVG

3. **Commission a Designer**:
   - Provide these specifications
   - Request multiple format exports (PNG, SVG)
   - Ensure rights for use in open-source context

### Current Avatar
The bot uses the **Vector Institute logo** as its avatar:
- `.github/bot-assets/avatar.webp` - WebP format (primary)
- `.github/bot-assets/avatar.svg` - SVG vector format

This ensures consistent branding with Vector Institute across all bot interactions.

## Textual Identity

### Bot Signature
All bot comments, commits, and messages should include this signature:

```markdown
---
🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
```

### Git Commit Identity
```
Name: aieng-bot[bot]
Email: aieng-bot@vectorinstitute.ai
```

### Co-author Tag
```
Co-authored-by: AI Engineering Maintenance Bot <aieng-bot@vectorinstitute.ai>
```

## Communication Style

### Tone
- **Professional** but friendly
- **Clear and concise**
- **Informative** without being verbose
- **Helpful** and action-oriented

### Message Patterns

#### Success Messages
```
✅ [Action completed successfully]

[Brief explanation of what was done]

---
🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
```

#### Working/In-Progress Messages
```
🔧 [Action in progress]

[Brief explanation of what's being done]

---
🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
```

#### Warning/Error Messages
```
⚠️ [Issue description]

[Explanation of the issue]
[What actions can be taken]

---
🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
```

#### Informational Messages
```
ℹ️ [Information title]

[Details]

---
🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
```

### Emoji Usage
Use emojis sparingly and consistently:
- ✅ Success, approval, completion
- ❌ Failure, error, rejection
- 🔧 Working on fixes, maintenance
- ⚠️ Warning, caution needed
- ℹ️ Information, FYI
- 🎉 Celebration (for merges)
- 🤖 Bot signature

## GitHub Profile Setup

### Profile Configuration (if using GitHub App)
- **Name**: AI Engineering Maintenance Bot
- **Username**: `aieng-bot`
- **Description**: Automated maintenance bot for Vector Institute AI Engineering repositories. Auto-merges PRs and fixes common issues.
- **Website**: Link to this repository or Vector Institute website
- **Avatar**: Use the designed avatar image

### Repository Configuration
In the repository settings (`.github/settings.yml` if using probot/settings):
```yaml
repository:
  name: aieng-bot
  description: AI Engineering Maintenance Bot for Vector Institute repositories
  homepage: https://github.com/VectorInstitute/aieng-bot
  topics:
    - automation
    - github-actions
    - dependabot
    - maintenance-bot
    - ai-engineering
```

## Branding Consistency

### Across All Platforms
Ensure consistency in:
1. **Naming**: Always use "AI Engineering Maintenance Bot" or "aieng-bot"
2. **Avatar**: Same image across GitHub, documentation, etc.
3. **Signature**: Always include the standard signature in bot communications
4. **Email**: Always use `aieng-bot@vectorinstitute.ai`
5. **Color scheme**: Maintain the blue/green/orange palette in any visual materials

## License and Attribution
- The bot identity should reflect that it's maintained by Vector Institute's AI Engineering team
- All bot communications should maintain professional standards
- Attribution to Vector Institute should be clear and consistent
