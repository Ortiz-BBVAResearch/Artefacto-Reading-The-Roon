# Reading the Room with AI — Enhanced Edition v2.3

Independent copy of v2.2; all prior versions preserved.

## Changes
- Corrected the document title/version to v2.3.
- Improved responsive stacking for shock sliders in the Simulator.
- Retained the original dataset, model code, coefficients, forecasts, and scenario comparison calculations.

## Browser testing
Automated Chromium rendering was performed with Playwright using HTML injection (`page.set_content`), because direct local navigation was blocked in the test environment. All six top-level tabs rendered without uncaught JavaScript exceptions in the v2.2 baseline; mobile horizontal overflow was absent on the Simulator at 390px. This is not equivalent to a full end-to-end hosted-server test, and external live updates were not validated.

## Run
From this folder: `python -m http.server 8000`; open `http://localhost:8000`.

Title-only variant: Model data heading renamed to "The US Economy in Motion: Data Evolution & Relations". Original v2.3 preserved.
