package main

// Formatting for the macOS panel load-failure log (panels_loadfail_darwin.go).
// Kept platform-neutral so the redaction is tested on every CI runner, not only
// where the ObjC delegate compiles.

import (
	"fmt"
	"net/url"
	"regexp"
)

// nsURLErrorATSRequiresSecureConnection is NSURLErrorDomain's code for a load
// App Transport Security refused (NSURLErrorAppTransportSecurityRequiresSecureConnection).
const nsURLErrorATSRequiresSecureConnection = -1022

// embeddedURL matches an absolute URL inside free text such as an error
// description.
var embeddedURL = regexp.MustCompile(`(?i)\b[a-z][a-z0-9+.\-]*://[^\s"'<>]+`)

// panelLoadFailureLine formats a failed panel load for sidecar.log, which the
// in-app Log Viewer can export. The delegate reports every failed main-frame
// load, including in-page navigations away from the brain, so a failing URL can
// carry the panel's access token or another site's secrets (an OAuth code, an
// #access_token fragment). Every URL, the ones inside the description too, is
// cut down to scheme://host/path before it is logged.
func panelLoadFailureLine(panelID, failingURL, domain string, code int, desc string) string {
	line := fmt.Sprintf("[panels] %s: page load failed: %s %d: %s",
		panelID, domain, code, embeddedURL.ReplaceAllStringFunc(desc, stripURLSecrets))
	if failingURL != "" {
		line += " url=" + stripURLSecrets(failingURL)
	}
	if domain == "NSURLErrorDomain" && code == nsURLErrorATSRequiresSecureConnection {
		line += " (App Transport Security refused a cleartext load; see packaging/macos/Info.plist)"
	}
	return line
}

// stripURLSecrets drops a URL's userinfo, query and fragment.
func stripURLSecrets(raw string) string {
	u, err := url.Parse(raw)
	if err != nil {
		return "[unparseable url]"
	}
	u.User = nil
	u.RawQuery = ""
	u.ForceQuery = false
	u.Fragment = ""
	u.RawFragment = ""
	return u.String()
}
