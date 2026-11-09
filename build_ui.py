#!/usr/bin/env python3
"""
DERLENG TV — Mini App UI & Sanitized Catalog Builder (v3.0)
Generates:
  1. index.html — Optimized Telegram Mini App with:
     - Non-blocking font & script loading (defer)
     - Progressive/chunked DOM rendering (60 items per batch via scroll observer)
     - Real-time Video Player Status Overlay (Loading, Connecting, Buffering, Muted badge, Error + Retry/Next)
     - Clean HLS.js + Native Safari lifecycle management, 20s progress watchdog timeout, and bounded retries
     - True Multi-Device Fullscreen (iOS native video, Android/Desktop/TV DOM + Telegram WebApp FS)
     - Dual query/hash + start_param reactive deep-link router
  2. channels_public.json — Sanitized full catalog with private query parameters and broken entries removed
"""

import os
import re
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_CHANNELS_PATH = os.path.join(BASE_DIR, 'channels.json')
PUBLIC_CHANNELS_PATH = os.path.join(BASE_DIR, 'channels_public.json')
INDEX_HTML_PATH = os.path.join(BASE_DIR, 'index.html')

from catalog import sanitize_catalog

def load_and_sanitize_channels():
    with open(RAW_CHANNELS_PATH, encoding='utf-8') as f:
        records = json.load(f)
    published, reasons = sanitize_catalog(records)
    private = sum(reasons.get(k, 0) for k in ('private_url', 'unapproved_query'))
    return published, private, sum(reasons.values()) - private


def select_embedded_bootstrap_channels(all_channels):
    bootstrap = []
    counts = {'KH': 0, 'Kids': 0, 'Sports': 0, 'News': 0, 'Movies': 0, 'Documentary': 0, 'Other': 0}
    limits = {'KH': 50, 'Kids': 70, 'Sports': 60, 'News': 60, 'Movies': 50, 'Documentary': 40, 'Other': 20}

    for ch in all_channels:
        if ch['g'] == 'Cambodia' or ch['c'] == 'KH':
            if counts['KH'] < limits['KH']:
                bootstrap.append(ch)
                counts['KH'] += 1
        elif ch['t'] in limits:
            if counts[ch['t']] < limits[ch['t']]:
                bootstrap.append(ch)
                counts[ch['t']] += 1
        else:
            if counts['Other'] < limits['Other']:
                bootstrap.append(ch)
                counts['Other'] += 1

    return bootstrap


def get_head_links():
    proto = 'ht' + 'tps://'
    tg_js = proto + 'telegram.org/js/telegram-web-app.js'
    hls_js = 'vendor/hls-1.7.4.min.js'
    gf_api = proto + 'fonts.googleapis.com'
    gf_stat = proto + 'fonts.gstatic.com'
    gf_css = gf_api + '/css2?family=Kantumruy+Pro:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap'
    return (
        f'  <link rel="preconnect" href="{gf_api}">\n'
        f'  <link rel="preconnect" href="{gf_stat}" crossorigin>\n'
        f'  <link href="{gf_css}" rel="stylesheet" >\n'
        f'  <script src="{tg_js}" defer></script>\n'
        f'  <script src="{hls_js}" defer></script>'
    )


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="km">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>DERLENG TV - ទូរទស្សន៍ផ្សាយផ្ទាល់</title>
  <link rel="icon" type="image/png" href="favicon.png">
  <link rel="apple-touch-icon" href="logo.png">
__HEAD_LINKS__
  <style>
    :root {
      --bg-dark: #0a0d14;
      --card-bg: rgba(22, 28, 45, 0.72);
      --card-border: rgba(255, 255, 255, 0.08);
      --card-hover: rgba(30, 41, 69, 0.88);
      --brand-cyan: #00f2fe;
      --brand-blue: #4facfe;
      --brand-gradient: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
      --brand-accent: #00d2ff;
      --live-red: #ff3344;
      --live-glow: rgba(255, 51, 68, 0.45);
      --text-main: #f8fafc;
      --text-dim: #94a3b8;
      --text-muted: #64748b;
      --radius-sm: 8px;
      --radius-md: 14px;
      --radius-lg: 20px;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-tap-highlight-color: transparent;
    }

    body {
      font-family: 'Plus Jakarta Sans', 'Kantumruy Pro', 'Khmer OS Siemreap', 'Khmer Sangam MN', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: radial-gradient(circle at 50% 0%, #151d30 0%, var(--bg-dark) 75%);
      color: var(--text-main);
      display: flex;
      flex-direction: column;
      height: 100vh;
      height: 100dvh;
      overflow: hidden;
      user-select: none;
    }

    /* Top Brand Bar */
    .brand-header {
      padding: 10px 16px;
      background: rgba(10, 13, 20, 0.88);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--card-border);
      z-index: 100;
      flex-shrink: 0;
    }

    .brand-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .brand-logo-img {
      width: 34px;
      height: 34px;
      border-radius: 9px;
      object-fit: cover;
      box-shadow: 0 4px 14px rgba(0, 242, 254, 0.35);
      border: 1px solid rgba(0, 242, 254, 0.35);
      flex-shrink: 0;
      background: #051026;
    }

    .brand-title-wrap {
      display: flex;
      flex-direction: column;
    }

    .brand-name {
      font-size: 15px;
      font-weight: 800;
      letter-spacing: 0.4px;
      display: flex;
      align-items: center;
      gap: 5px;
    }

    .brand-tv-pill {
      background: var(--brand-gradient);
      color: #031024;
      font-size: 10px;
      font-weight: 900;
      padding: 1px 5px;
      border-radius: 4px;
      letter-spacing: 0.5px;
    }

    .brand-sub {
      font-size: 10px;
      color: var(--text-muted);
      font-weight: 500;
      margin-top: 1px;
    }

    .live-status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 10px;
      background: rgba(255, 51, 68, 0.12);
      border: 1px solid rgba(255, 51, 68, 0.3);
      border-radius: 20px;
      font-size: 11px;
      font-weight: 700;
      color: #ff5252;
      letter-spacing: 0.4px;
    }

    .live-pulse {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #ff3344;
      box-shadow: 0 0 10px #ff3344;
      animation: pulse 1.6s infinite;
    }

    @keyframes pulse {
      0% { transform: scale(0.95); box-shadow: 0 0 0 0 var(--live-glow); }
      70% { transform: scale(1.15); box-shadow: 0 0 0 8px rgba(255, 51, 68, 0); }
      100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 51, 68, 0); }
    }

    /* Video Player Stage */
    #player-wrap {
      position: relative;
      width: 100%;
      background: #000;
      z-index: 90;
      display: flex;
      flex-direction: column;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.7);
      flex-shrink: 0;
    }

    .video-viewport {
      position: relative;
      width: 100%;
      background: #000;
      aspect-ratio: 16 / 9;
      max-height: clamp(165px, 29vh, 240px);
      overflow: hidden;
    }

    video {
      width: 100%;
      height: 100%;
      object-fit: contain;
      background: #000;
      display: block;
    }

    /* Stream Status & Diagnostic Overlay */
    #player-status-overlay {
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: rgba(6, 9, 15, 0.78);
      backdrop-filter: blur(6px);
      -webkit-backdrop-filter: blur(6px);
      z-index: 25;
      padding: 16px;
      text-align: center;
      transition: opacity 0.2s ease;
    }

    #player-status-overlay.hidden {
      opacity: 0;
      pointer-events: none;
    }

    .status-spinner {
      width: 34px;
      height: 34px;
      border-radius: 50%;
      border: 3px solid rgba(0, 242, 254, 0.18);
      border-top-color: var(--brand-cyan);
      animation: spin 0.85s linear infinite;
      margin-bottom: 10px;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .status-title {
      font-size: 13px;
      font-weight: 700;
      color: #fff;
      margin-bottom: 4px;
    }

    .status-sub {
      font-size: 11px;
      color: var(--text-dim);
      max-width: 280px;
      line-height: 1.4;
    }

    .status-actions {
      display: none;
      align-items: center;
      gap: 8px;
      margin-top: 12px;
    }

    .status-btn {
      padding: 6px 13px;
      border-radius: 16px;
      font-size: 11.5px;
      font-weight: 700;
      font-family: inherit;
      cursor: pointer;
      border: 1px solid rgba(255, 255, 255, 0.15);
      background: rgba(255, 255, 255, 0.08);
      color: #fff;
      transition: all 0.2s;
    }

    .status-btn.primary {
      background: var(--brand-gradient);
      color: #031024;
      border-color: transparent;
    }

    .status-btn:active {
      transform: scale(0.95);
    }

    /* Unmute Floating Pill */
    #unmute-pill {
      position: absolute;
      top: 10px;
      right: 12px;
      z-index: 30;
      background: rgba(10, 14, 24, 0.85);
      border: 1px solid rgba(0, 242, 254, 0.45);
      color: var(--brand-cyan);
      padding: 5px 11px;
      border-radius: 16px;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
      display: none;
      align-items: center;
      gap: 5px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
    }

    /* True Multi-Device Fullscreen System (Phone, Tablet, Desktop, TV) */
    body.is-fullscreen {
      overflow: hidden !important;
      background: #000 !important;
    }

    body.is-fullscreen .brand-header,
    body.is-fullscreen #controls,
    body.is-fullscreen .list-header,
    body.is-fullscreen #channel-list {
      display: none !important;
    }

    #player-wrap:fullscreen,
    #player-wrap:-webkit-full-screen,
    body.is-fullscreen #player-wrap {
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      right: 0 !important;
      bottom: 0 !important;
      width: 100vw !important;
      width: 100dvw !important;
      height: 100vh !important;
      height: 100dvh !important;
      max-height: 100vh !important;
      max-height: 100dvh !important;
      margin: 0 !important;
      padding: 0 !important;
      border: none !important;
      border-radius: 0 !important;
      background: #000 !important;
      z-index: 99999999 !important;
    }

    #player-wrap:fullscreen .video-viewport,
    #player-wrap:-webkit-full-screen .video-viewport,
    body.is-fullscreen #player-wrap .video-viewport {
      width: 100vw !important;
      height: 100vh !important;
      height: 100dvh !important;
      max-height: 100vh !important;
      max-height: 100dvh !important;
      aspect-ratio: auto !important;
      background: #000 !important;
    }

    #player-wrap:fullscreen video,
    #player-wrap:-webkit-full-screen video,
    body.is-fullscreen #player-wrap video {
      width: 100vw !important;
      height: 100vh !important;
      height: 100dvh !important;
      object-fit: contain !important;
      background: #000 !important;
    }

    #player-wrap:fullscreen .now-playing-bar,
    #player-wrap:-webkit-full-screen .now-playing-bar,
    body.is-fullscreen #player-wrap .now-playing-bar {
      position: absolute !important;
      bottom: 0 !important;
      left: 0 !important;
      right: 0 !important;
      background: linear-gradient(0deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.3) 60%, transparent 100%) !important;
      border-bottom: none !important;
      z-index: 100000000 !important;
      padding: 12px max(20px, env(safe-area-inset-right)) max(12px, env(safe-area-inset-bottom)) max(20px, env(safe-area-inset-left)) !important;
      opacity: 0 !important;
      pointer-events: none !important;
      transition: opacity 0.3s ease !important;
    }

    body.is-fullscreen #player-wrap .now-playing-bar:focus-within,
    #player-wrap:fullscreen:hover .now-playing-bar,
    #player-wrap:-webkit-full-screen:hover .now-playing-bar,
    body.is-fullscreen #player-wrap:hover .now-playing-bar,
    body.is-fullscreen #player-wrap .now-playing-bar.show-overlay,
    #player-wrap:fullscreen .now-playing-bar.show-overlay,
    #player-wrap:-webkit-full-screen .now-playing-bar.show-overlay {
      opacity: 1 !important;
      pointer-events: auto !important;
    }

    #player-wrap.hide-cursor,
    #player-wrap.hide-cursor * {
      cursor: none !important;
    }

    /* Player Status & Now Playing Bar */
    .now-playing-bar {
      padding: 8px 16px;
      background: linear-gradient(180deg, #121826 0%, #0d121c 100%);
      border-bottom: 1px solid var(--card-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .now-info {
      flex: 1;
      min-width: 0;
    }

    .now-label {
      font-size: 10px;
      text-transform: uppercase;
      font-weight: 700;
      letter-spacing: 0.6px;
      color: var(--brand-accent);
      margin-bottom: 2px;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .now-state-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--brand-cyan);
      display: inline-block;
    }

    .now-title {
      font-size: 13.5px;
      font-weight: 700;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: #fff;
    }

    .now-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .action-btn {
      width: 30px;
      height: 30px;
      border-radius: 50%;
      border: 1px solid var(--card-border);
      background: rgba(255, 255, 255, 0.06);
      color: var(--text-dim);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s;
    }

    .action-btn:active {
      background: var(--brand-gradient);
      color: #000;
      transform: scale(0.92);
    }

    /* Controls: Search & Category Filter */
    #controls {
      padding: 10px 14px 6px 14px;
      background: transparent;
      display: flex;
      flex-direction: column;
      gap: 9px;
      flex-shrink: 0;
    }

    .search-container {
      position: relative;
      display: flex;
      align-items: center;
    }

    .search-icon {
      position: absolute;
      left: 14px;
      font-size: 14px;
      color: var(--text-muted);
      pointer-events: none;
    }

    #search {
      width: 100%;
      padding: 9px 38px;
      border-radius: var(--radius-md);
      border: 1px solid rgba(255, 255, 255, 0.09);
      background: rgba(20, 27, 45, 0.65);
      color: #fff;
      font-size: 13px;
      font-family: inherit;
      outline: none;
      transition: border-color 0.2s ease, background 0.2s ease;
    }

    #search:focus {
      border-color: var(--brand-accent);
      background: rgba(22, 32, 54, 0.92);
      box-shadow: 0 0 0 3px rgba(0, 242, 254, 0.15);
    }

    #search::placeholder {
      color: var(--text-muted);
      font-size: 13px;
    }

    .clear-search-btn {
      position: absolute;
      right: 12px;
      font-size: 13px;
      color: var(--text-muted);
      background: none;
      border: none;
      cursor: pointer;
      display: none;
      padding: 4px;
    }

    /* Category Navigation */
    #cat-bar {
      display: flex;
      gap: 7px;
      overflow-x: auto;
      padding-bottom: 2px;
      scrollbar-width: none;
      -webkit-overflow-scrolling: touch;
    }

    #cat-bar::-webkit-scrollbar {
      display: none;
    }

    .cat-btn {
      padding: 6.5px 13px;
      border-radius: var(--radius-lg);
      font-size: 11.5px;
      font-weight: 700;
      font-family: inherit;
      background: rgba(25, 34, 56, 0.58);
      border: 1px solid var(--card-border);
      color: var(--text-dim);
      white-space: nowrap;
      cursor: pointer;
      outline: none;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      gap: 5px;
    }

    .cat-btn[hidden] { display: none; }

    .cat-btn.active {
      background: var(--brand-gradient);
      color: #031024;
      border-color: transparent;
      box-shadow: 0 4px 14px rgba(0, 210, 255, 0.32);
    }

    /* Channel List Section */
    .list-header {
      padding: 4px 16px 6px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      flex-shrink: 0;
    }

    #channel-list {
      flex: 1 1 auto;
      overflow-y: auto;
      padding: 0 14px 28px 14px;
      -webkit-overflow-scrolling: touch;
      display: flex;
      flex-direction: column;
      gap: 7px;
    }

    .channel-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 14px;
      border-radius: var(--radius-md);
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      cursor: pointer;
      transition: background 0.15s ease, border-color 0.15s ease;
      gap: 12px;
      flex-shrink: 0;
    }

    .channel-row:hover {
      background: var(--card-hover);
      border-color: rgba(255, 255, 255, 0.15);
    }

    .channel-row.active {
      background: rgba(0, 180, 255, 0.14);
      border: 1px solid rgba(0, 242, 254, 0.45);
      box-shadow: 0 4px 14px rgba(0, 210, 255, 0.12);
    }

    .ch-left {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
      flex: 1;
    }

    .ch-icon-badge {
      width: 38px;
      height: 38px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      flex-shrink: 0;
    }

    .ch-icon-badge { position: relative; overflow: hidden; flex-shrink: 0; }
    .channel-logo { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; padding: 3px; background: #f8fafc; }
    .channel-logo[hidden] { display: none; }
    .channel-initials { font-size: 12px; font-weight: 800; }
    .channel-row.active .ch-icon-badge {
      background: rgba(0, 242, 254, 0.15);
      border-color: rgba(0, 242, 254, 0.4);
    }

    .ch-text {
      min-width: 0;
      flex: 1;
    }

    .ch-name {
      font-size: 13.5px;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-bottom: 2px;
    }

    .channel-row.active .ch-name {
      color: var(--brand-cyan);
    }

    .ch-meta-row {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      color: var(--text-dim);
    }

    .ch-tag {
      padding: 1px 6px;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.06);
      font-size: 9.5px;
      font-weight: 600;
      color: var(--text-muted);
    }

    .channel-row.active .ch-tag {
      background: rgba(0, 242, 254, 0.12);
      color: var(--brand-cyan);
    }

    .ch-right {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      flex-shrink: 0;
    }

    .play-arrow {
      font-size: 13px;
      color: var(--text-muted);
    }

    .equalizer {
      display: flex;
      align-items: flex-end;
      gap: 2.5px;
      height: 15px;
      width: 14px;
    }

    .equalizer span {
      flex: 1;
      background: var(--brand-cyan);
      border-radius: 1px;
      animation: eq-bounce 1s ease-in-out infinite alternate;
    }

    .equalizer span:nth-child(1) { height: 60%; animation-delay: 0.1s; }
    .equalizer span:nth-child(2) { height: 100%; animation-delay: 0.3s; }
    .equalizer span:nth-child(3) { height: 40%; animation-delay: 0.5s; }

    @keyframes eq-bounce {
      0% { height: 20%; }
      50% { height: 100%; }
      100% { height: 35%; }
    }

    .empty-state {
      padding: 40px 20px;
      text-align: center;
      color: var(--text-muted);
      font-size: 13px;
    }

    .empty-icon {
      font-size: 32px;
      margin-bottom: 8px;
      opacity: 0.6;
    }

    /* Responsive layout: CSS Grid needs no extra runtime or device detection. */
    body { padding: env(safe-area-inset-top, 0px) env(safe-area-inset-right, 0px) env(safe-area-inset-bottom, 0px) env(safe-area-inset-left, 0px); }
    #channel-list, #controls, #player-wrap { min-width: 0; min-height: 0; }
    #search { font-size: 16px; min-height: 44px; }
    .cat-btn { flex-shrink: 0; min-height: 44px; }
    .action-btn, .clear-search-btn { min-width: 44px; min-height: 44px; }
    .channel-row { min-height: 64px; }
    .video-viewport { max-height: min(36dvh, 420px); }
    button:focus-visible, .channel-row:focus-visible, video:focus-visible {
      outline: 3px solid var(--brand-accent); outline-offset: -3px;
      box-shadow: inset 0 0 0 5px #031024;
    }
    .now-playing-bar:focus-within { opacity: 1 !important; pointer-events: auto !important; }
    @media (min-width: 600px) and (min-height: 700px) {
      #channel-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-content: start; }
      .channel-row { min-width: 0; }
    }
    @media (min-width: 1000px), (min-width: 560px) and (orientation: landscape) {
      body:not(.is-fullscreen) {
        display: grid;
        grid-template-columns: minmax(0, 1fr) clamp(320px, 34vw, 540px);
        grid-template-rows: auto auto auto minmax(0, 1fr);
        grid-template-areas: 'brand brand' 'player controls' 'player heading' 'player channels';
      }
      .brand-header { grid-area: brand; }
      #player-wrap { grid-area: player; align-self: stretch; justify-content: center; }
      .video-viewport { max-height: calc(100dvh - 150px); aspect-ratio: 16 / 9; }
      #controls { grid-area: controls; }
      .list-header { grid-area: heading; }
      #channel-list { grid-area: channels; display: flex; padding-bottom: 16px; }
      #cat-bar { flex-wrap: wrap; max-height: 150px; overflow-y: auto; }
      .cat-btn { font-size: 13px; }
      .now-playing-bar { flex-shrink: 0; }
    }
    @media (max-height: 600px) and (min-width: 560px) {
      .brand-header { padding-top: 4px; padding-bottom: 4px; }
      #cat-bar { flex-wrap: nowrap; max-height: none; }
      .video-viewport { max-height: calc(100dvh - 130px); }
    }
    @media (min-width: 1800px) {
      body:not(.is-fullscreen) { grid-template-columns: minmax(0, 1fr) clamp(540px, 32vw, 900px); }
      .brand-header { padding: 20px 28px; }
      .brand-logo-img { width: 52px; height: 52px; }
      .brand-name { font-size: 28px; }
      #controls { padding: 20px 24px; }
      #search, #search::placeholder, .cat-btn { font-size: clamp(18px, 1vw, 32px); }
      .cat-btn { min-height: 56px; padding: 10px 18px; }
      #cat-bar { max-height: 240px; gap: 10px; }
      #channel-list { gap: 12px; }
      .channel-row { min-height: 90px; padding: 18px; }
      .ch-name { font-size: clamp(20px, 1.1vw, 36px); }
      .ch-meta-row, .list-header { font-size: clamp(14px, .8vw, 26px); }
      .ch-icon-badge { width: 56px; height: 56px; }
      .action-btn { min-width: 56px; min-height: 56px; font-size: 24px; }
    }
    @media (max-width: 359px) {
      .brand-header { padding: 8px; gap: 6px; }
      .brand-sub { display: none; }
      .live-badge { font-size: 10px; padding: 5px; }
      .video-viewport { max-height: 25dvh; }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
    }
  </style>
</head>
<body>

  <!-- Brand Header -->
  <header class="brand-header">
    <div class="brand-left">
      <img class="brand-logo-img" src="logo.png" alt="DERLENG TV" width="34" height="34">
      <div class="brand-title-wrap">
        <div class="brand-name">DERLENG <span class="brand-tv-pill">TV</span></div>
        <div class="brand-sub">ទូរទស្សន៍ផ្សាយផ្ទាល់ • កម្ពុជា & សកលលោក</div>
      </div>
    </div>
    <div class="live-status-pill">
      <span class="live-pulse"></span> ផ្សាយផ្ទាល់ HD
    </div>
  </header>

  <!-- Cinema Video Player Stage -->
  <section id="player-wrap">
    <div class="video-viewport">
      <video id="video" controls autoplay playsinline></video>

      <!-- Muted Autoplay Unmute Pill -->
      <button id="unmute-pill" type="button" title="បើកសំឡេង (Unmute)">
        🔇 ចុចដើម្បីបើកសំឡេង
      </button>

      <!-- Real-Time Stream Status & Error Recovery Overlay -->
      <div id="player-status-overlay">
        <div class="status-spinner" id="status-spinner"></div>
        <div class="status-title" id="status-title">កំពុងភ្ជាប់ប៉ុស្តិ៍ផ្សាយផ្ទាល់...</div>
        <div class="status-sub" id="status-sub">សូមរង់ចាំបន្តិច • Connecting to live stream</div>
        <div class="status-actions" id="status-actions">
          <button class="status-btn primary" id="retry-stream-btn" type="button">↻ សាកល្បងម្ដងទៀត</button>
          <button class="status-btn" id="next-stream-btn" type="button">⏭ ប៉ុស្តិ៍បន្ទាប់</button>
        </div>
      </div>
    </div>

    <div class="now-playing-bar">
      <div class="now-info">
        <div class="now-label">
          <span class="now-state-dot" id="now-state-dot"></span>
          <span id="now-state-text">កំពុងចាក់ផ្សាយ</span>
        </div>
        <div class="now-title" id="now-title">Apsara TV 11 HD</div>
      </div>
      <div class="now-actions">
        <button class="action-btn" id="fullscreen-btn" type="button" title="ពង្រីកពេញអេក្រង់ (Cinema Mode)">⛶</button>
        <button class="action-btn" id="reload-btn" type="button" title="ផ្ទុកឡើងវិញ (Reload)">↻</button>
      </div>
    </div>
  </section>

  <!-- Search & Category Filter -->
  <section id="controls">
    <div class="search-container">
      <span class="search-icon">🔍</span>
      <input type="text" id="search" placeholder="ស្វែងរកប៉ុស្តិ៍ (ឈ្មោះ, ប្រទេស...)" autocomplete="off">
      <button class="clear-search-btn" id="clear-search" type="button">✕</button>
    </div>

    <div id="cat-bar">
      <button class="cat-btn active" data-cat="Cambodia" type="button"><span>🇰🇭</span> កម្ពុជា</button>
      <button class="cat-btn" data-cat="ALL" type="button"><span>🌍</span> ប៉ុស្តិ៍ទាំងអស់</button>
      <button class="cat-btn" data-cat="Kids" type="button"><span>🧸</span> កុមារ</button>
      <button class="cat-btn" data-cat="Sports" type="button"><span>⚽</span> កីឡា</button>
      <button class="cat-btn" data-cat="News" type="button"><span>📰</span> ព័ត៌មាន</button>
      <button class="cat-btn" data-cat="Movies" type="button"><span>🎬</span> ភាពយន្ត</button>
      <button class="cat-btn" data-cat="Documentary" type="button"><span>📚</span> ឯកសារ</button>
      <button class="cat-btn" data-cat="Music" type="button"><span>🎵</span> តន្ត្រី</button>
      <button class="cat-btn" data-cat="Education" type="button"><span>🎓</span> អប់រំ</button>
      <button class="cat-btn" data-cat="Religious" type="button"><span>🕊️</span> សាសនា</button>
      <button class="cat-btn" data-cat="Business" type="button"><span>📈</span> ពាណិជ្ជកម្ម</button>
      <button class="cat-btn" data-cat="Lifestyle" type="button"><span>✨</span> របៀបរស់នៅ</button>
      <button class="cat-btn" data-cat="Entertainment" type="button"><span>🎭</span> កម្សាន្ត</button>
      <button class="cat-btn" data-cat="General" type="button"><span>📺</span> ទូទៅ</button>
    </div>
  </section>

  <!-- Channel List Header -->
  <div class="list-header">
    <span id="category-heading">ប៉ុស្តិ៍ជាតិកម្ពុជា</span>
    <span id="channel-count">១២ ប៉ុស្តិ៍</span>
  </div>

  <!-- Progressive Channel List Container -->
  <main id="channel-list"></main>

  <script>
    function initTelegramSDK() {
      try {
        if (window.Telegram && window.Telegram.WebApp) {
          window.Telegram.WebApp.ready();
          window.Telegram.WebApp.expand();
          try {
            window.Telegram.WebApp.setHeaderColor('#0a0d14');
            window.Telegram.WebApp.setBackgroundColor('#0a0d14');
          } catch (e) {}
        }
      } catch (e) {}
    }
    initTelegramSDK();
    window.addEventListener('DOMContentLoaded', initTelegramSDK);

    let channels = BOOTSTRAP_CHANNELS_PLACEHOLDER;
    let fullCatalogLoaded = false;

    const video = document.getElementById('video');
    const nowTitle = document.getElementById('now-title');
    const nowStateText = document.getElementById('now-state-text');
    const nowStateDot = document.getElementById('now-state-dot');
    const listEl = document.getElementById('channel-list');
    const searchInput = document.getElementById('search');
    const clearSearchBtn = document.getElementById('clear-search');
    const reloadBtn = document.getElementById('reload-btn');
    const fullscreenBtn = document.getElementById('fullscreen-btn');
    const catBtns = document.querySelectorAll('.cat-btn');
    const catHeading = document.getElementById('category-heading');
    const chCount = document.getElementById('channel-count');

    const statusOverlay = document.getElementById('player-status-overlay');
    const statusSpinner = document.getElementById('status-spinner');
    const statusTitle = document.getElementById('status-title');
    const statusSub = document.getElementById('status-sub');
    const statusActions = document.getElementById('status-actions');
    const retryStreamBtn = document.getElementById('retry-stream-btn');
    const nextStreamBtn = document.getElementById('next-stream-btn');
    const unmutePill = document.getElementById('unmute-pill');

    const RENDER_BATCH_SIZE = 60;
    let renderedCount = 0;
    let currentCat = 'Cambodia';
    let currentIdx = 0;
    let currentChannel = null;
    let hls = null;
    let playSessionId = 0;
    let streamWatchdogTimer = null;
    let retryTimer = null;
    let bufferingTimer = null;
    let retryAttemptCount = 0;
    let hlsNetworkRetryCount = 0;
    let hlsMediaRetryCount = 0;
    let nativeFallbackUsed = false;
    let sessionListeners = [];
    let hlsWaitTimer = null;
    let lastMediaTime = 0;
    let lastProgressAt = 0;
    let failurePending = false;
    let playerSuspended = false;
    let pendingCatalogLink = false;
    const MAX_AUTO_RETRIES = 2;
    const MAX_HLS_NETWORK_RETRIES = 1;
    const STREAM_TIMEOUT_MS = 20000;

    window.activeFiltered = [];

    function getChannelIcon(ch) {
      if (ch.g === 'Cambodia' || ch.c === 'KH') return '🇰🇭';
      if (ch.t === 'Kids') return '🧸';
      if (ch.t === 'Sports') return '⚽';
      if (ch.t === 'News') return '📰';
      if (ch.t === 'Movies') return '🎬';
      if (ch.t === 'Documentary') return '📚';
      return '📺';
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function setPlayerState(state, detailText) {
      if (!statusOverlay) return;
      if (state === 'PLAYING') {
        statusOverlay.classList.add('hidden');
        nowStateText.textContent = 'កំពុងចាក់ផ្សាយ • LIVE';
        nowStateDot.style.background = '#00f2fe';
        unmutePill.style.display = video.muted ? 'inline-flex' : 'none';
        return;
      }

      statusOverlay.classList.remove('hidden');
      if (state === 'LOADING_CHANNEL' || state === 'CONNECTING_STREAM' || state === 'BUFFERING') {
        statusSpinner.style.display = 'block';
        statusActions.style.display = 'none';
        nowStateDot.style.background = '#f59e0b';
        if (state === 'LOADING_CHANNEL') {
          statusTitle.textContent = 'កំពុងបើកប៉ុស្តិ៍...';
          statusSub.textContent = detailText || 'Loading channel...';
          nowStateText.textContent = 'កំពុងបើកប៉ុស្តិ៍...';
        } else if (state === 'CONNECTING_STREAM') {
          statusTitle.textContent = 'កំពុងភ្ជាប់ប្រព័ន្ធផ្សាយ...';
          statusSub.textContent = detailText || 'Connecting to live stream...';
          nowStateText.textContent = 'កំពុងភ្ជាប់...';
        } else {
          statusTitle.textContent = 'កំពុងផ្ទុកទិន្នន័យវីដេអូ...';
          statusSub.textContent = detailText || 'Buffering live stream...';
          nowStateText.textContent = 'កំពុងផ្ទុក...';
        }
      } else if (state === 'NETWORK_DISCONNECTED') {
        statusSpinner.style.display = 'none';
        statusActions.style.display = 'flex';
        nowStateDot.style.background = '#ff3344';
        nowStateText.textContent = 'ដាច់អ៊ីនធឺណិត • OFFLINE';
        statusTitle.textContent = '📡 ដាច់ការភ្ជាប់អ៊ីនធឺណិត';
        statusSub.textContent = detailText || 'សូមពិនិត្យមើលសេវាអ៊ីនធឺណិតរបស់អ្នក រួចចុចសាកល្បងម្ដងទៀត។';
      } else {
        statusSpinner.style.display = 'none';
        statusActions.style.display = 'flex';
        nowStateDot.style.background = '#ff3344';
        nowStateText.textContent = 'រអាក់រអួល • UNAVAILABLE';
        statusTitle.textContent = '⚠️ ប៉ុស្តិ៍នេះមិនអាចចាក់បានទេនៅពេលនេះ';
        statusSub.textContent = detailText || 'ប្រភពផ្សាយអាចកំពុងផ្អាក ឬរអាក់រអួល។ សូមសាកល្បងម្ដងទៀត ឬប្តូរប៉ុស្តិ៍។';
      }
    }

    function clearBufferingTimer() {
      if (bufferingTimer !== null) {
        clearTimeout(bufferingTimer);
        bufferingTimer = null;
      }
    }

    function recordMediaProgress() {
      const advanced = !video.paused && !video.seeking &&
        video.currentTime > lastMediaTime + 0.01;
      if (advanced) {
        lastProgressAt = Date.now();
        clearBufferingTimer();
        setPlayerState('PLAYING');
      }
      lastMediaTime = video.currentTime;
      return advanced;
    }

    function scheduleBuffering(sid, name) {
      // 'stalled' describes network fetching, not necessarily playback.
      // Ignore brief gaps; require a full grace period without media progress.
      if (bufferingTimer !== null) return;
      const startTime = video.currentTime;
      bufferingTimer = setTimeout(() => {
        bufferingTimer = null;
        if (sid !== playSessionId || failurePending || playerSuspended ||
            document.hidden || video.paused) return;
        if (video.currentTime > startTime + 0.01) {
          recordMediaProgress();
          return;
        }
        setPlayerState('BUFFERING', name);
      }, 1200);
    }

    function clearTimers() {
      clearBufferingTimer();
      if (streamWatchdogTimer) {
        clearTimeout(streamWatchdogTimer);
        streamWatchdogTimer = null;
      }
      if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = null;
      }
    }

    function destroyCurrentPlayer() {
      clearTimers();
      if (hlsWaitTimer) { clearInterval(hlsWaitTimer); hlsWaitTimer = null; }
      sessionListeners.forEach(([name, fn]) => video.removeEventListener(name, fn));
      sessionListeners = [];
      if (hls) {
        try { hls.stopLoad(); hls.detachMedia(); hls.destroy(); } catch (e) {}
        hls = null;
      }
      if (video) {
        try { video.pause(); video.removeAttribute('src'); video.load(); } catch (e) {}
      }
    }

    function listenForSession(name, fn, sid) {
      const guarded = () => { if (sid === playSessionId && !failurePending) fn(); };
      video.addEventListener(name, guarded);
      sessionListeners.push([name, guarded]);
    }

    function watchProgress(sid) {
      streamWatchdogTimer = setTimeout(() => {
        if (sid !== playSessionId || failurePending || playerSuspended) return;
        if (document.hidden) { lastProgressAt = Date.now(); watchProgress(sid); return; }
        // Also sample the clock when a browser throttles timeupdate events.
        recordMediaProgress();
        if (!video.paused && Date.now() - lastProgressAt >= STREAM_TIMEOUT_MS) {
          handleStreamFailure(sid, 'ការផ្សាយមិនឆ្លើយតប (Stream stalled)។');
          return;
        }
        // A source that never starts must time out too; a user pause after progress is intentional.
        if (lastMediaTime === 0 && Date.now() - lastProgressAt >= STREAM_TIMEOUT_MS) {
          handleStreamFailure(sid, 'ការភ្ជាប់ចំណាយពេលយូរពេក (Connection timeout)។');
          return;
        }
        watchProgress(sid);
      }, 1000);
    }

    function startPlaybackWithMutedFallback(sid) {
      if (sid !== playSessionId || !video || failurePending) return;
      Promise.resolve().then(() => {
        if (sid !== playSessionId || failurePending) return;
        return video.play();
      }).catch(() => {
        if (sid !== playSessionId || failurePending) return;
        video.muted = true;
        unmutePill.style.display = 'inline-flex';
        return video.play();
      }).catch(() => {
        if (sid !== playSessionId || failurePending) return;
        failurePending = true;
        clearTimers();
        setPlayerState('PLAYBACK_FAILED', 'ចុច Play ឬសាកល្បងម្ដងទៀតដើម្បីចាប់ផ្ដើម។');
      });
    }

    if (video) video.addEventListener('volumechange', () => {
      unmutePill.style.display = video.muted ? 'inline-flex' : 'none';
    });

    if (unmutePill) {
      unmutePill.addEventListener('click', (e) => {
        e.stopPropagation();
        if (video) {
          video.muted = false;
          video.volume = 1.0;
          unmutePill.style.display = 'none';
        }
      });
    }

    function handleStreamFailure(sessionId, customReason) {
      if (sessionId !== playSessionId || failurePending) return;
      failurePending = true;
      destroyCurrentPlayer();

      if (!navigator.onLine) {
        setPlayerState('NETWORK_DISCONNECTED');
        return;
      }

      const usesHttpRelay = (
        currentChannel &&
        currentChannel.u &&
        currentChannel.u.indexOf('http:') === 0
      );

      // Bounded application-level retry policy (applies to all streams)
      if (retryAttemptCount < MAX_AUTO_RETRIES) {
        retryAttemptCount++;
        const delayMs = retryAttemptCount * 1200;
        setPlayerState(
          'CONNECTING_STREAM',
          `កំពុងភ្ជាប់ឡើងវិញដោយស្វ័យប្រវត្តិ (${retryAttemptCount}/${MAX_AUTO_RETRIES})...`
        );
        retryTimer = setTimeout(() => {
          if (sessionId === playSessionId) {
            play(currentIdx, true);
          }
        }, delayMs);
        return;
      }

      // Budget exhausted: Present informative diagnosis with actionable retry buttons
      const reasonMsg = (usesHttpRelay
        ? 'HTTP stream relay could not load this channel. Please try again.'
        : customReason || 'ប្រភពផ្សាយមិនឆ្លើយតប ឬកំពុងផ្អាកដំណើរការបណ្ដោះអាសន្ន។');
      setPlayerState('STREAM_UNAVAILABLE', reasonMsg);
    }

    function play(idx, isRetry = false) {
      if (!window.activeFiltered || window.activeFiltered.length === 0) {
        window.activeFiltered = channels.filter(ch => (ch.g === 'Cambodia' || ch.c === 'KH'));
      }
      const ch = isRetry && currentChannel ? currentChannel : window.activeFiltered[idx];
      if (!ch) return;
      // Keep canonical URL-based IDs/deep links; try a verified HTTPS preference first.
      // Existing bounded retry falls back to the original source/HTTP relay.
      const sourceUrl = (!isRetry || retryAttemptCount === 0) ? (ch.p || ch.u) : ch.u;
      const mediaUrl = sourceUrl.startsWith('http://') ? '/relay.php?cid=' + encodeURIComponent(ch.id) : sourceUrl;

      playSessionId++;
      const sessionId = playSessionId;
      if (!isRetry) {
        retryAttemptCount = 0;
      }
      hlsNetworkRetryCount = 0;
      hlsMediaRetryCount = 0;
      nativeFallbackUsed = false;
      failurePending = false;
      playerSuspended = false;

      currentIdx = idx;
      currentChannel = ch;
      if (nowTitle) nowTitle.textContent = ch.n;
      updateActiveRowIndicator();

      destroyCurrentPlayer();

      if (!navigator.onLine) {
        setPlayerState('NETWORK_DISCONNECTED');
        return;
      }

      setPlayerState('CONNECTING_STREAM', ch.n);

      lastMediaTime = 0;
      lastProgressAt = Date.now();
      listenForSession('timeupdate', recordMediaProgress, sessionId);
      listenForSession('waiting', () => scheduleBuffering(sessionId, ch.n), sessionId);
      listenForSession('stalled', () => scheduleBuffering(sessionId, ch.n), sessionId);
      // An event alone must neither claim LIVE nor reset the no-progress watchdog.
      listenForSession('playing', recordMediaProgress, sessionId);
      watchProgress(sessionId);

      const attachAndPlay = () => {
        if (sessionId !== playSessionId || failurePending) return;

        if (typeof Hls !== 'undefined' && Hls.isSupported()) {
          hls = new Hls({
            enableWorker: true,
            lowLatencyMode: true,
            maxBufferLength: 12,
            manifestLoadingTimeOut: 10000,
            manifestLoadingMaxRetry: 2,
            levelLoadingTimeOut: 10000,
            fragLoadingTimeOut: 12000
          });
          hls.loadSource(mediaUrl);
          hls.attachMedia(video);
          hls.on(Hls.Events.MANIFEST_PARSED, () => {
            if (sessionId !== playSessionId) return;
            scheduleBuffering(sessionId, ch.n);
            startPlaybackWithMutedFallback(sessionId);
          });
          const tryNativeOrFailure = (sid) => {
            if (sid === playSessionId && !failurePending && !nativeFallbackUsed && video && video.canPlayType('application/vnd.apple.mpegurl')) {
              try { if (hls) { hls.destroy(); hls = null; } } catch (e) {}
              nativeFallbackUsed = true;
              listenForSession('error', () => handleStreamFailure(sid), sid);
              video.src = mediaUrl;
              startPlaybackWithMutedFallback(sid);
            } else {
              handleStreamFailure(sid);
            }
          };

          hls.on(Hls.Events.ERROR, (event, data) => {
            if (sessionId !== playSessionId) return;
            if (!data.fatal) return;
            switch (data.type) {
              case Hls.ErrorTypes.NETWORK_ERROR:
                if (hlsNetworkRetryCount < MAX_HLS_NETWORK_RETRIES) {
                  hlsNetworkRetryCount++;
                  try {
                    hls.startLoad();
                  } catch (e) {
                    tryNativeOrFailure(sessionId);
                  }
                } else {
                  tryNativeOrFailure(sessionId);
                }
                break;
              case Hls.ErrorTypes.MEDIA_ERROR:
                if (hlsMediaRetryCount++ >= 1) { tryNativeOrFailure(sessionId); break; }
                try {
                  hls.recoverMediaError();
                } catch (e) {
                  tryNativeOrFailure(sessionId);
                }
                break;
              default:
                tryNativeOrFailure(sessionId);
                break;
            }
          });
        } else if (video && video.canPlayType('application/vnd.apple.mpegurl')) {
          video.src = mediaUrl;
          listenForSession('loadedmetadata', () => startPlaybackWithMutedFallback(sessionId), sessionId);
          listenForSession('error', () => handleStreamFailure(sessionId), sessionId);
        } else if (video) {
          handleStreamFailure(sessionId, 'កម្មវិធីរុករកនេះមិនគាំទ្រ HLS។');
        }
      };

      if (typeof Hls === 'undefined' && !(video && video.canPlayType('application/vnd.apple.mpegurl'))) {
        let waitPolls = 0;
        hlsWaitTimer = setInterval(() => {
          waitPolls++;
          if (sessionId !== playSessionId) {
            clearInterval(hlsWaitTimer); hlsWaitTimer = null;
            return;
          }
          if (typeof Hls !== 'undefined' || waitPolls >= 25) {
            clearInterval(hlsWaitTimer); hlsWaitTimer = null;
            attachAndPlay();
          }
        }, 80);
      } else {
        attachAndPlay();
      }
    }

    function getCountryLabel(ch) {
      if (ch.country_basis === 'origin_unknown_curated_feed_market' && ch.mg)
        return ch.mg + ' (feed; origin unverified)';
      if (ch.country_basis === 'unresolved' || ch.c === 'ZZ') return 'Country unverified';
      return ch.g || 'Country unverified';
    }

    function buildChannelRowHtml(ch, idx) {
      const isPlaying = (currentChannel && currentChannel.u === ch.u);
      const activeClass = isPlaying ? ' active' : '';
      const initials = ch.n.split(/\s+/).filter(Boolean).slice(0, 2).map(w => Array.from(w)[0]).join('').toUpperCase();
      const logo = typeof ch.l === 'string' && /^logos\/[a-f0-9]{64}\.webp$/.test(ch.l)
        ? '<img class="channel-logo" src="' + ch.l + '" alt="' + escapeHtml(ch.n) + ' logo" loading="lazy" decoding="async" width="44" height="44">' : '';
      const icon = '<span class="channel-initials" aria-hidden="true">' + escapeHtml(initials) + '</span>' + logo;
      const rightIndicator = isPlaying
        ? '<div class="equalizer"><span></span><span></span><span></span></div>'
        : '<div class="play-arrow">▶</div>';

      return (
        '<div class="channel-row' + activeClass + '" data-idx="' + idx + '" role="button" tabindex="0">' +
          '<div class="ch-left">' +
            '<div class="ch-icon-badge">' + icon + '</div>' +
            '<div class="ch-text">' +
              '<div class="ch-name">' + escapeHtml(ch.n) + '</div>' +
              '<div class="ch-meta-row">' +
                '<span>' + escapeHtml(getCountryLabel(ch)) + '</span>' +
                '<span class="ch-tag">' + escapeHtml(ch.t || 'Live') + '</span>' +
              '</div>' +
            '</div>' +
          '</div>' +
          '<div class="ch-right">' + rightIndicator + '</div>' +
        '</div>'
      );
    }

    function appendNextBatch() {
      if (!window.activeFiltered || renderedCount >= window.activeFiltered.length) return;
      const nextEnd = Math.min(renderedCount + RENDER_BATCH_SIZE, window.activeFiltered.length);
      let chunkHtml = '';
      for (let i = renderedCount; i < nextEnd; i++) {
        chunkHtml += buildChannelRowHtml(window.activeFiltered[i], i);
      }
      listEl.insertAdjacentHTML('beforeend', chunkHtml);
      renderedCount = nextEnd;
    }

    function updateActiveRowIndicator() {
      const rows = listEl.querySelectorAll('.channel-row');
      rows.forEach(row => {
        const idx = parseInt(row.getAttribute('data-idx'), 10);
        const ch = window.activeFiltered[idx];
        const isPlaying = (ch && currentChannel && ch.u === currentChannel.u);
        const rightEl = row.querySelector('.ch-right');
        if (isPlaying) {
          row.classList.add('active');
          if (rightEl) rightEl.innerHTML = '<div class="equalizer"><span></span><span></span><span></span></div>';
        } else {
          row.classList.remove('active');
          if (rightEl) rightEl.innerHTML = '<div class="play-arrow">▶</div>';
        }
      });
    }

    function render() {
      catBtns.forEach(btn => {
        const cat = btn.dataset.cat;
        const count = channels.filter(ch => cat === 'ALL' || (cat === 'Cambodia' && (ch.c === 'KH' || ch.g === 'Cambodia')) || ch.t === cat).length;
        btn.hidden = count === 0;
        btn.title = count.toLocaleString() + ' channels';
        btn.setAttribute('aria-label', btn.textContent.trim() + ' (' + count.toLocaleString() + ')');
      });
      const q = searchInput.value.toLowerCase().trim();
      clearSearchBtn.style.display = q ? 'block' : 'none';

      window.activeFiltered = channels.filter(ch => {
        const isKh = (ch.g === 'Cambodia' || ch.c === 'KH');
        const matchCat = (currentCat === 'ALL') || (currentCat === 'Cambodia' && isKh) || (ch.t === currentCat);
        const matchQ = !q || ch.n.toLowerCase().includes(q) || (ch.g && ch.g.toLowerCase().includes(q)) || (ch.mg && ch.mg.toLowerCase().includes(q));
        return matchCat && matchQ;
      });

      const catNamesKh = {
        'Cambodia': 'ប៉ុស្តិ៍ជាតិកម្ពុជា',
        'Kids': 'ប៉ុស្តិ៍កុមារ & តុក្កតា',
        'Sports': 'ប៉ុស្តិ៍កីឡាផ្សាយផ្ទាល់',
        'News': 'ប៉ុស្តិ៍ព័ត៌មាន ២៤/៧',
        'Movies': 'ប៉ុស្តិ៍ភាពយន្ត & កុន',
        'Documentary': 'ប៉ុស្តិ៍ភាពយន្តឯកសារ',
        'Music': 'ប៉ុស្តិ៍តន្ត្រី',
        'Education': 'ប៉ុស្តិ៍អប់រំ',
        'Religious': 'ប៉ុស្តិ៍សាសនា',
        'Business': 'ប៉ុស្តិ៍ពាណិជ្ជកម្ម',
        'Lifestyle': 'ប៉ុស្តិ៍របៀបរស់នៅ',
        'Entertainment': 'ប៉ុស្តិ៍កម្សាន្ត',
        'General': 'ប៉ុស្តិ៍ទូទៅ',
        'ALL': 'ប៉ុស្តិ៍ផ្សាយទាំងអស់'
      };
      catHeading.textContent = catNamesKh[currentCat] || (currentCat === 'ALL' ? 'ប៉ុស្តិ៍ទាំងអស់' : currentCat);
      chCount.textContent = window.activeFiltered.length.toLocaleString() + ' ប៉ុស្តិ៍';

      if (window.activeFiltered.length === 0) {
        listEl.innerHTML = '<div class="empty-state"><div class="empty-icon">📺</div>រកមិនឃើញប៉ុស្តិ៍ដែលត្រូវគ្នាទេ</div>';
        renderedCount = 0;
        return;
      }

      listEl.innerHTML = '';
      renderedCount = 0;
      appendNextBatch();
    }

    // Capture image failures without inline handlers (release CSP forbids them).
    listEl.addEventListener('error', event => {
      if (event.target.matches('.channel-logo')) event.target.hidden = true;
    }, true);

    listEl.addEventListener('click', event => {
      const row = event.target.closest('.channel-row');
      if (row) play(Number(row.dataset.idx));
    });
    listEl.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        const row = event.target.closest('.channel-row');
        if (row) { event.preventDefault(); play(Number(row.dataset.idx)); }
      }
    });

    listEl.addEventListener('scroll', () => {
      if (listEl.scrollTop + listEl.clientHeight >= listEl.scrollHeight - 280) {
        appendNextBatch();
      }
    }, { passive: true });

    catBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        catBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentCat = btn.dataset.cat;
        listEl.scrollTop = 0;
        render();
      });
    });

    let searchTimer = null;
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        listEl.scrollTop = 0;
        render();
      }, 60);
    });

    clearSearchBtn.addEventListener('click', () => {
      searchInput.value = '';
      listEl.scrollTop = 0;
      render();
    });

    function triggerReloadCurrent() {
      if (currentChannel) {
        retryAttemptCount = 0;
        play(currentIdx, true);
      }
    }

    reloadBtn.addEventListener('click', triggerReloadCurrent);
    if (retryStreamBtn) retryStreamBtn.addEventListener('click', triggerReloadCurrent);
    if (nextStreamBtn) {
      nextStreamBtn.addEventListener('click', () => {
        if (window.activeFiltered && window.activeFiltered.length > 0) {
          const nextIdx = (currentIdx + 1) % window.activeFiltered.length;
          if (nextIdx >= renderedCount) appendNextBatch();
          play(nextIdx, false);
        }
      });
    }

    window.addEventListener('online', () => {
      if (currentChannel && video && video.paused) {
        triggerReloadCurrent();
      }
    });
    window.addEventListener('offline', () => {
      playSessionId++;
      failurePending = true;
      destroyCurrentPlayer();
      setPlayerState('NETWORK_DISCONNECTED');
    });

    const wrap = document.getElementById('player-wrap');
    const nowBar = document.querySelector('.now-playing-bar');
    let controlsHideTimeout = null;

    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const isIPhone = /iPhone|iPod/.test(navigator.userAgent);

    function isCurrentlyFullscreen() {
      const tg = window.Telegram?.WebApp;
      return (
        document.body.classList.contains('is-fullscreen') ||
        !!document.fullscreenElement ||
        !!document.webkitFullscreenElement ||
        !!document.mozFullScreenElement ||
        !!document.msFullscreenElement ||
        (video && video.webkitDisplayingFullscreen) ||
        (tg && tg.isFullscreen)
      );
    }

    function syncFullscreenUI(isFullscreen) {
      if (fullscreenBtn) {
        if (isFullscreen) {
          fullscreenBtn.textContent = '🗗';
          fullscreenBtn.setAttribute('title', 'បង្រួមអេក្រង់ (Exit Fullscreen)');
        } else {
          fullscreenBtn.textContent = '⛶';
          fullscreenBtn.setAttribute('title', 'ពង្រីកពេញអេក្រង់ (Cinema Fullscreen)');
        }
      }
      if (isFullscreen) {
        document.body.classList.add('is-fullscreen');
      } else {
        document.body.classList.remove('is-fullscreen');
        wrap.classList.remove('hide-cursor');
        clearTimeout(controlsHideTimeout);
        nowBar.classList.remove('show-overlay');
      }
    }

    function exitFullScreenMode() {
      const tg = window.Telegram?.WebApp;
      document.body.classList.remove('is-fullscreen');
      wrap.classList.remove('hide-cursor');

      if (tg && typeof tg.unlockOrientation === 'function') {
        try { tg.unlockOrientation(); } catch (e) {}
      }
      if (screen.orientation && typeof screen.orientation.unlock === 'function') {
        try { screen.orientation.unlock(); } catch (e) {}
      }
      if (video && typeof video.webkitExitFullscreen === 'function' && video.webkitDisplayingFullscreen) {
        try { video.webkitExitFullscreen(); } catch (e) {}
      }
      try {
        if (document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement) {
          if (document.exitFullscreen) document.exitFullscreen().catch(() => {});
          else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
          else if (document.mozCancelFullScreen) document.mozCancelFullScreen();
          else if (document.msExitFullscreen) document.msExitFullscreen();
        }
      } catch (e) {}
      if (tg && typeof tg.exitFullscreen === 'function' && tg.isFullscreen) {
        try { tg.exitFullscreen(); } catch (e) {}
      }
      syncFullscreenUI(false);
    }

    function enterFullScreenMode() {
      const tg = window.Telegram?.WebApp;
      if (isIPhone && video && typeof video.webkitEnterFullscreen === 'function') {
        try {
          video.webkitEnterFullscreen();
          syncFullscreenUI(true);
          return;
        } catch (e) {}
      }
      document.body.classList.add('is-fullscreen');
      if (tg && typeof tg.requestFullscreen === 'function' && !tg.isFullscreen) {
        try { tg.requestFullscreen(); } catch (e) {}
      }
      if (tg && typeof tg.lockOrientation === 'function') {
        try { tg.lockOrientation('landscape'); } catch (e) {}
      }
      if (screen.orientation && typeof screen.orientation.lock === 'function') {
        try { screen.orientation.lock('landscape').catch(() => {}); } catch (e) {}
      }
      try {
        if (!document.fullscreenElement && !document.webkitFullscreenElement && !document.mozFullScreenElement && !document.msFullscreenElement) {
          if (wrap.requestFullscreen) wrap.requestFullscreen().catch(() => {});
          else if (wrap.webkitRequestFullscreen) wrap.webkitRequestFullscreen();
          else if (wrap.webkitRequestFullScreen) wrap.webkitRequestFullScreen();
          else if (wrap.mozRequestFullScreen) wrap.mozRequestFullScreen();
          else if (wrap.msRequestFullscreen) wrap.msRequestFullscreen();
          else if (video && typeof video.webkitEnterFullscreen === 'function') video.webkitEnterFullscreen();
        }
      } catch (e) {}
      syncFullscreenUI(true);
      resetControlsTimeout();
    }

    function toggleFullScreen() {
      if (isCurrentlyFullscreen()) exitFullScreenMode();
      else enterFullScreenMode();
    }

    if (fullscreenBtn) {
      fullscreenBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleFullScreen();
      });
    }

    if (video) {
      video.addEventListener('webkitbeginfullscreen', () => syncFullscreenUI(true));
      video.addEventListener('webkitendfullscreen', () => syncFullscreenUI(false));
    }

    ['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'].forEach(evt => {
      document.addEventListener(evt, () => {
        const hasNativeFs = !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement);
        if (!hasNativeFs && !(video && video.webkitDisplayingFullscreen) && !window.Telegram?.WebApp?.isFullscreen) {
          syncFullscreenUI(false);
        } else if (hasNativeFs) {
          syncFullscreenUI(true);
        }
      });
    });

    if (window.Telegram?.WebApp?.onEvent) {
      window.Telegram.WebApp.onEvent('fullscreenChanged', () => {
        syncFullscreenUI(!!window.Telegram.WebApp.isFullscreen || !!document.fullscreenElement || !!video.webkitDisplayingFullscreen);
      });
    }

    wrap.addEventListener('dblclick', (e) => {
      if (e.target.closest('.action-btn') || e.target.closest('.status-btn')) return;
      toggleFullScreen();
    });

    function resetControlsTimeout() {
      wrap.classList.remove('hide-cursor');
      nowBar.classList.add('show-overlay');
      clearTimeout(controlsHideTimeout);
      if (isCurrentlyFullscreen()) {
        controlsHideTimeout = setTimeout(() => {
          nowBar.classList.remove('show-overlay');
          if (!video.paused) wrap.classList.add('hide-cursor');
        }, 3000);
      }
    }

    wrap.addEventListener('focusin', resetControlsTimeout);
    wrap.addEventListener('mousemove', resetControlsTimeout);
    wrap.addEventListener('touchstart', resetControlsTimeout, { passive: true });
    wrap.addEventListener('click', (e) => {
      if (e.target.closest('.action-btn') || e.target.closest('.status-btn') || e.target.closest('#unmute-pill')) return;
      if (isCurrentlyFullscreen()) {
        if (nowBar.classList.contains('show-overlay')) {
          nowBar.classList.remove('show-overlay');
          clearTimeout(controlsHideTimeout);
        } else {
          resetControlsTimeout();
        }
      }
    });

    document.addEventListener('keydown', (e) => {
      if (document.activeElement && document.activeElement.tagName === 'INPUT') {
        if (e.key === 'Escape') document.activeElement.blur();
        return;
      }
      const isBackKey = (e.key === 'Escape' || e.keyCode === 27 || e.keyCode === 10009 || e.keyCode === 461 || e.keyCode === 8 || e.keyCode === 220);
      if (isBackKey && isCurrentlyFullscreen()) {
        e.preventDefault();
        exitFullScreenMode();
        return;
      }
      if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        toggleFullScreen();
        return;
      }
      if (e.defaultPrevented || (e.target.closest && e.target.closest('button, [role=button], a'))) return;
      const isPlayPauseKey = (e.key === ' ' || e.code === 'Space' || e.keyCode === 13 || e.keyCode === 65385 || e.keyCode === 179 || e.keyCode === 415);
      if (isPlayPauseKey) {
        e.preventDefault();
        if (video.paused) video.play().catch(() => {});
        else video.pause();
        resetControlsTimeout();
        return;
      }
      if (e.key === 'm' || e.key === 'M') {
        e.preventDefault();
        video.muted = !video.muted;
        resetControlsTimeout();
        return;
      }
    });

    document.addEventListener('keydown', e => {
      if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return;
      if (e.target.matches('input, textarea, video')) return;
      const items = Array.from(document.querySelectorAll('button, .channel-row[tabindex], input'))
        .filter(el => !el.disabled && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
      if (!items.length) return;
      const active = document.activeElement;
      if (!items.includes(active)) { e.preventDefault(); items[0].focus(); return; }
      const rect = active.getBoundingClientRect();
      const x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
      const horizontal = e.key === 'ArrowLeft' || e.key === 'ArrowRight';
      const sign = e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 1;
      let best = null, score = Infinity;
      items.forEach(el => {
        if (el === active) return;
        const r = el.getBoundingClientRect();
        const dx = r.x + r.width / 2 - x, dy = r.y + r.height / 2 - y;
        const along = (horizontal ? dx : dy) * sign;
        const across = Math.abs(horizontal ? dy : dx);
        if (along > 2 && along + across * 3 < score) { best = el; score = along + across * 3; }
      });
      if (best) { e.preventDefault(); best.focus(); best.scrollIntoView({block: 'nearest', inline: 'nearest'}); }
    });

    function safeDecode(val) {
      if (!val) return '';
      try { return decodeURIComponent(val); } catch (e) { return val; }
    }

    function getParam(key) {
      try {
        const sp = new URLSearchParams(window.location.search);
        if (sp.has(key) && sp.get(key)) return safeDecode(sp.get(key));
      } catch (e) {}
      try {
        if (window.location.hash) {
          const rawHash = window.location.hash.replace(/^#/, '');
          const hp = new URLSearchParams(rawHash);
          if (hp.has(key) && hp.get(key)) return safeDecode(hp.get(key));
          const qIdx = rawHash.indexOf('?');
          if (qIdx !== -1) {
            const subHp = new URLSearchParams(rawHash.substring(qIdx + 1));
            if (subHp.has(key) && subHp.get(key)) return safeDecode(subHp.get(key));
          }
        }
      } catch (e) {}
      try {
        const regex = new RegExp('[?&#]' + key + '=([^&#]*)', 'i');
        const match = window.location.href.match(regex);
        if (match && match[1]) return safeDecode(match[1]);
      } catch (e) {}
      try {
        const tgParam = window.Telegram?.WebApp?.initDataUnsafe?.start_param;
        if (tgParam && key === 'cid') return safeDecode(tgParam);
      } catch (e) {}
      return null;
    }

    function normStr(str) {
      if (!str) return '';
      return safeDecode(str).toLowerCase().replace(/[^a-z0-9]/g, '');
    }

    let lastNavKey = null;

    function handleNavigation(forceReeval = false) {
      const reqId = getParam('cid');
      const reqName = getParam('name') || getParam('ch');
      const reqCat = getParam('cat');
      const navKey = `${reqCat || ''}|${reqName || ''}|${reqId || ''}`;
      if (!forceReeval && lastNavKey === navKey && currentChannel) return;
      const found = reqId ? channels.find(ch => ch.id === reqId) :
        (reqName ? channels.find(ch => ch.n === reqName) : null);
      if ((reqId || reqName) && !found) {
        pendingCatalogLink = !fullCatalogLoaded;
        destroyCurrentPlayer();
        playSessionId++;
        setPlayerState(fullCatalogLoaded ? 'STREAM_UNAVAILABLE' : 'LOADING_CHANNEL',
          fullCatalogLoaded ? 'ប៉ុស្តិ៍នេះមិនមានក្នុងបញ្ជីផ្សាយទេ។' : 'កំពុងផ្ទុកបញ្ជីប៉ុស្តិ៍...');
        render();
        return;
      }
      pendingCatalogLink = false;

      if (reqCat) {
        currentCat = reqCat;
      } else if (found) {
        if (found.g === 'Cambodia' || found.c === 'KH') currentCat = 'Cambodia';
        else if (found.t && Array.from(catBtns).some(btn => btn.dataset.cat === found.t)) currentCat = found.t;
        else currentCat = 'ALL';
      }

      catBtns.forEach(btn => {
        if (btn.dataset.cat.toLowerCase() === currentCat.toLowerCase()) {
          catBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          currentCat = btn.dataset.cat;
        }
      });

      render();

      let playIdx = -1;
      if (found) {
        playIdx = window.activeFiltered.findIndex(ch => ch.u === found.u);
      }

      if (playIdx === -1 && found) {
        currentCat = 'ALL';
        catBtns.forEach(btn => {
          if (btn.dataset.cat === 'ALL') {
            catBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
          }
        });
        render();
        playIdx = window.activeFiltered.findIndex(ch => ch.u === found.u);
      }

      if (playIdx === -1) playIdx = 0;

      while (playIdx >= renderedCount && renderedCount < window.activeFiltered.length) {
        appendNextBatch();
      }

      if (window.activeFiltered.length > 0 && playIdx >= 0) {
        lastNavKey = navKey;
        play(playIdx);
        setTimeout(() => {
          const activeCard = document.querySelector('.channel-row.active');
          if (activeCard) activeCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 250);
      }
    }

    handleNavigation();

    // Versioned data asset prevents mixed releases; failure preserves the bootstrap.
    setTimeout(() => {
      const xhr = new XMLHttpRequest();
      xhr.open('GET', 'CATALOG_FILENAME_PLACEHOLDER', true);
      xhr.timeout = 12000;
      const catalogFailed = () => {
        if (pendingCatalogLink) setPlayerState('STREAM_UNAVAILABLE', 'មិនអាចផ្ទុកបញ្ជីប៉ុស្តិ៍បាន។ សូមផ្ទុកទំព័រឡើងវិញ។');
      };
      xhr.onerror = catalogFailed;
      xhr.ontimeout = catalogFailed;
      xhr.onload = function () {
        if (xhr.status !== 200) { catalogFailed(); return; }
        try {
          const fullData = JSON.parse(xhr.responseText);
          if (!Array.isArray(fullData) || !fullData.every(ch =>
              ch && typeof ch.id === 'string' && typeof ch.n === 'string' &&
              typeof ch.u === 'string' && /^https?:\/\//.test(ch.u) && ch.protocol === 'hls')) {
            catalogFailed(); return;
          }
          channels = fullData;
          fullCatalogLoaded = true;
          if (pendingCatalogLink) { handleNavigation(true); return; }
          render();
          if (currentChannel) currentIdx = window.activeFiltered.findIndex(ch => ch.id === currentChannel.id);
        } catch (e) { catalogFailed(); }
      };
      xhr.send();
    }, 300);

    window.addEventListener('hashchange', () => handleNavigation(false));
    window.addEventListener('popstate', () => handleNavigation(false));
    window.addEventListener('pagehide', () => { playerSuspended = true; playSessionId++; destroyCurrentPlayer(); });
    window.addEventListener('pageshow', () => {
      if (playerSuspended && currentChannel) triggerReloadCurrent();
      else handleNavigation(false);
    });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        lastProgressAt = Date.now();
        if (playerSuspended && currentChannel) triggerReloadCurrent();
        else handleNavigation(false);
      }
    });
  </script>
</body>
</html>
"""


def build_all(output_dir=None):
    import hashlib
    from pathlib import Path
    out = Path(output_dir or Path(BASE_DIR) / 'dist' / 'hostinger')
    out.mkdir(parents=True, exist_ok=True)
    with open(RAW_CHANNELS_PATH, encoding='utf-8') as f:
        sanitized, rejected = sanitize_catalog(json.load(f))
    if not sanitized:
        raise ValueError('Refusing to publish an empty catalog')
    catalog_bytes = json.dumps(sanitized, ensure_ascii=False, separators=(',', ':')).encode()
    version = hashlib.sha256(catalog_bytes).hexdigest()[:16]
    catalog_name = f'channels.{version}.json'
    bootstrap = select_embedded_bootstrap_channels(sanitized)
    bootstrap_json = json.dumps(bootstrap, ensure_ascii=False, separators=(',', ':'))
    bootstrap_json = bootstrap_json.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    final_html = (HTML_TEMPLATE.replace('__HEAD_LINKS__', get_head_links())
                  .replace('BOOTSTRAP_CHANNELS_PLACEHOLDER', bootstrap_json)
                  .replace('CATALOG_FILENAME_PLACEHOLDER', catalog_name))
    assets = {catalog_name: catalog_bytes, 'channels_public.json': catalog_bytes,
              'index.html': final_html.encode()}
    for name, content in assets.items():
        temp = out / (name + '.tmp')
        temp.write_bytes(content)
        temp.replace(out / name)
    report = {'catalog_version': version, 'published': len(sanitized), 'rejected': rejected,
              'availability': 'unverified', 'hosting': 'static-https', 'base_url': 'https://tv.derlenghub.com'}
    (out.parent / 'catalog-build-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Build static Hostinger-compatible Mini App (no production writes).')
    parser.add_argument('--output-dir')
    build_all(parser.parse_args().output_dir)
