//go:build darwin

package main

// macOS: log why a panel page failed to load. WKWebView reports a failed load
// only to its navigation delegate, and the vendored engine installs none, so an
// ATS refusal, a DNS miss or a refused connection left nothing in sidecar.log:
// the reveal fallback then showed a window with nothing in it (issue #442's
// "completely white" panel). This installs a delegate that only logs those
// failures. It implements no policy, authentication or process-termination
// method, so WebKit keeps its default for every decision (including reloading
// after a web content process crash, which implementing
// webViewWebContentProcessDidTerminate: would switch off).
//
// PER-VIEW, unlike the new-window hook in panels_extnav_darwin.go: the delegate
// is set on each panel's WKWebView, so the settings / log / hosted windows are
// untouched.
//
// Delegate lifetime: WKWebView.navigationDelegate is a WEAK reference, so the
// delegate is pinned to the view as an associated object.
//
// COMPILE-UNVERIFIED locally: CGO/ObjC, built only on macOS (CI's
// sidecar-build-darwin job compiles it), same caveat as tray_darwin.go.

/*
#cgo darwin CFLAGS: -x objective-c -fobjc-arc
#cgo darwin LDFLAGS: -framework Cocoa -framework WebKit
#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>
#import <objc/runtime.h>
#include <stdlib.h>

extern void goPanelLoadFailed(char* panelID, char* failingURL, char* domain, long code, char* desc);

static const char kJarvisPanelNavDelegateKey;

@interface JarvisPanelNavDelegate : NSObject <WKNavigationDelegate>
@property (nonatomic, copy) NSString *panelID;
@end

@implementation JarvisPanelNavDelegate
- (void)jarvisReport:(NSError *)error {
    if (!error) return;
    // A superseded load (a new navigation replacing one still in flight)
    // reports NSURLErrorCancelled. That is not a failure worth logging.
    if ([error.domain isEqualToString:NSURLErrorDomain] && error.code == NSURLErrorCancelled) return;
    // WebKitErrorDomain 102 (frame load interrupted) is still logged: it is
    // noise for a download link, but it is also the reason when a panel URL
    // returns content WebKit will not render.
    id failing = error.userInfo[NSURLErrorFailingURLStringErrorKey];
    if (![failing isKindOfClass:[NSString class]]) {
        id failingNSURL = error.userInfo[NSURLErrorFailingURLErrorKey];
        failing = [failingNSURL isKindOfClass:[NSURL class]] ? [(NSURL *)failingNSURL absoluteString] : nil;
    }
    NSString *failingURL = [failing isKindOfClass:[NSString class]] ? (NSString *)failing : @"";
    goPanelLoadFailed((char *)self.panelID.UTF8String,
                      (char *)failingURL.UTF8String,
                      (char *)error.domain.UTF8String,
                      (long)error.code,
                      (char *)error.localizedDescription.UTF8String);
}
- (void)webView:(WKWebView *)webView didFailProvisionalNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    (void)webView; (void)navigation;
    [self jarvisReport:error];
}
- (void)webView:(WKWebView *)webView didFailNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    (void)webView; (void)navigation;
    [self jarvisReport:error];
}
@end

// Returns 0 when the delegate is installed, 1 when the view already has a
// navigation delegate (left alone: whoever set it owns those decisions), 2 when
// there is no view.
static int jarvisInstallPanelLoadFailureLog(void* wkwebview, const char* panelID) {
    if (!wkwebview) return 2;
    // __bridge, not __bridge_transfer: the engine owns the view.
    WKWebView* v = (__bridge WKWebView*)wkwebview;
    if (v.navigationDelegate) return 1;
    JarvisPanelNavDelegate* d = [JarvisPanelNavDelegate new];
    NSString* pid = panelID ? [NSString stringWithUTF8String:panelID] : nil;
    d.panelID = pid ?: @"";
    objc_setAssociatedObject(v, &kJarvisPanelNavDelegateKey, d,
                             OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    v.navigationDelegate = d;
    return 0;
}
*/
import "C"

import (
	"log"
	"unsafe"

	webview "github.com/webview/webview_go"
)

// installPanelLoadFailureLog wires the logging delegate onto a panel's webview.
// Best-effort: a failure only loses the log line, never the panel. Called on
// the UI thread before the first Navigate.
func installPanelLoadFailureLog(wv webview.WebView, id PanelID) {
	ctrl := webview.BrowserController(wv)
	if ctrl == nil {
		log.Printf("[panels] spawn(%s): no browser controller; page load failures will not be logged", id)
		return
	}
	cid := C.CString(string(id))
	defer C.free(unsafe.Pointer(cid))
	switch C.jarvisInstallPanelLoadFailureLog(ctrl, cid) {
	case 0:
	case 1:
		log.Printf("[panels] spawn(%s): webview already has a navigation delegate; page load failures will not be logged", id)
	default:
		log.Printf("[panels] spawn(%s): no webview; page load failures will not be logged", id)
	}
}
