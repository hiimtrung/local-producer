// The Lucent bundle is a plain script that reads React from window when it runs; publish it before it loads.
import * as React from "react";

declare global {
  interface Window {
    React: typeof React;
  }
}

window.React = React;
