# Privacy and User-Asset Boundaries

This repository contains workflow instructions, templates, and helper scripts only.

## What must never enter this repository

- Raw photos or private reference images
- User character turnarounds and character specifications
- Local absolute paths, account names, credentials, or private identifiers
- Source articles supplied by users
- Generated article illustrations or review sheets
- EXIF or other source-photo metadata

## Local user data

The Skill stores reusable user IP packages outside the repository, by default under:

```text
~/.agents/personal-ip-article-illustrations/
```

Users may override this with `PERSONAL_IP_HOME`. Removing the Skill does not remove this directory.

## Image services

When a user chooses an image-generation service, a raw photo may be sent to that service only for the current private inference request. The Skill must not preserve the photo or its local path afterward.

## Rights

User IP packages default to `license: private`. The repository's MIT License does not grant rights to any user's photo, turnaround, character specification, article, or generated image.
