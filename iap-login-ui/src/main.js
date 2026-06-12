import firebase from 'firebase/compat/app';
import 'firebase/compat/auth';
import * as firebaseui from 'firebaseui';
import * as ciap from 'gcip-iap';
import 'firebaseui/dist/firebaseui.css';

const config = window.firebaseConfig || {};
const apiKey = config.apiKey || "";
const projectNumber = config.projectIdNumber || "";

if (!apiKey || !projectNumber) {
  console.error("Firebase config is missing API Key or Project Number. Cannot initialize IAP Login UI.");
} else {
  const params = new URLSearchParams(window.location.search);
  if ((window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") && (!params.get('apiKey') || !params.get('mode'))) {
    params.set('apiKey', apiKey);
    params.set('mode', 'login');
    params.set('tid', `_${projectNumber}`);
    params.set('state', 'local-dev-state');
    params.set('redirect_uri', 'http://localhost:5173/');
    window.location.search = params.toString();
  } else {
    const configs = {
      [apiKey]: {
        authDomain: config.authDomain,
        displayMode: 'optionFirst',
        tenants: {
          '*': {
            displayName: 'Nova Horizon Credit Union',
            signInOptions: [
              {
                provider: firebase.auth.GoogleAuthProvider.PROVIDER_ID,
                customParameters: {
                  prompt: 'select_account'
                }
              }
            ],
            immediateFederatedRedirect: false,
            signInFlow: 'redirect'
          }
        }
      }
    };

    const handler = new firebaseui.auth.FirebaseUiHandler(
      '#firebaseui-auth-container',
      configs
    );

    const ciapInstance = new ciap.Authentication(handler);
    ciapInstance.start();
  }
}
