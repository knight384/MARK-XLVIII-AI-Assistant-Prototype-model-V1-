package main

import (
	"strings"
	"testing"
)

func TestPanelLoadFailureLine_StripsURLSecrets(t *testing.T) {
	line := panelLoadFailureLine("tray:chat",
		"http://100.100.53.74:3142/?token=secret-tok#/",
		"NSURLErrorDomain", -1004,
		"Could not connect to http://100.100.53.74:3142/?token=secret-tok#/.")
	if strings.Contains(line, "secret-tok") {
		t.Fatalf("access token leaked into the log line: %q", line)
	}
	for _, want := range []string{"tray:chat", "NSURLErrorDomain -1004", "url=http://100.100.53.74:3142/"} {
		if !strings.Contains(line, want) {
			t.Errorf("expected %q in %q", want, line)
		}
	}
}

func TestPanelLoadFailureLine_StripsForeignSecrets(t *testing.T) {
	line := panelLoadFailureLine("tray:chat",
		"https://user:pw@idp.example.com/cb?code=oauth-code&state=s1#access_token=frag-tok",
		"WebKitErrorDomain", 102,
		"Frame load interrupted at https://idp.example.com/cb?code=oauth-code#access_token=frag-tok")
	for _, secret := range []string{"oauth-code", "frag-tok", "pw@", "state=s1"} {
		if strings.Contains(line, secret) {
			t.Errorf("%q leaked into the log line: %q", secret, line)
		}
	}
	if !strings.Contains(line, "url=https://idp.example.com/cb") {
		t.Errorf("expected the stripped url in %q", line)
	}
}

func TestPanelLoadFailureLine_UnparseableURL(t *testing.T) {
	line := panelLoadFailureLine("tray:chat", "http://[::1/?token=secret-tok", "NSURLErrorDomain", -1000, "bad url")
	if strings.Contains(line, "secret-tok") || !strings.Contains(line, "url=[unparseable url]") {
		t.Errorf("expected an unparseable url placeholder, got %q", line)
	}
}

func TestPanelLoadFailureLine_ATSHint(t *testing.T) {
	ats := panelLoadFailureLine("tray:chat", "", "NSURLErrorDomain", nsURLErrorATSRequiresSecureConnection, "insecure")
	if !strings.Contains(ats, "App Transport Security") {
		t.Errorf("expected an ATS hint for -1022, got %q", ats)
	}
	other := panelLoadFailureLine("tray:chat", "", "NSURLErrorDomain", -1004, "refused")
	if strings.Contains(other, "App Transport Security") {
		t.Errorf("unexpected ATS hint for -1004: %q", other)
	}
}
