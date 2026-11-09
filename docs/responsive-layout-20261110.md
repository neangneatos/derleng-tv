# Responsive layout and fullscreen — 2026-11-10

- Phones retain stacked player and channel navigation, 44px minimum primary controls, 16px search text and browser zoom support.
- Portrait tablets use a two-column channel grid. Wide screens and landscape viewports from 560px use a player/channel split layout.
- Desktop video is no longer capped at 240px. TV-sized viewports enlarge channel labels and controls.
- Short landscape windows no longer forcibly hide channel navigation; use the fullscreen button for cinema mode.
- Keyboard focus is visible. Directional keys navigate buttons/channel rows; Enter activates the focused control without also toggling playback.
- Fullscreen preserves video proportions (letterboxing may remain). Native fullscreen is requested where supported; CSS cinema mode is the fallback. iPhone native video fullscreen is preserved.
- Native fullscreen exit now clears cinema mode; Escape/Back restores browsing. Safe-area padding protects fullscreen controls, and keyboard focus reveals controls.

Validation: 27 Python tests and 19 synthetic Chromium scenarios, including 12 layout sizes (320x480 through 3840x2160), seven fullscreen sizes, native fullscreen exit, navigation and existing playback regressions. Real candidate playback passed for Fresh News and Andorra TV. Physical iPhone/iPad/Android/TV remote behavior is not certified by viewport emulation. Upstream availability and browser codec/autoplay policies are unchanged.

Evidence: workspace outputs/tv-responsive-20261110. Both source folders produce release 189e72e4c8c2fbae; catalog unchanged (6,064 entries). See live verification evidence before claiming deployment complete.
