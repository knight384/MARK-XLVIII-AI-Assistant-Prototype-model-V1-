//go:build !darwin

package main

import webview "github.com/webview/webview_go"

// installPanelLoadFailureLog is macOS-only (panels_loadfail_darwin.go). WebView2
// and WebKitGTK have no ATS, so the silent refusal it diagnoses does not happen
// there.
func installPanelLoadFailureLog(wv webview.WebView, id PanelID) { _, _ = wv, id }
