import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Shield, 
  Heart,
  Activity,
  Phone,
  Wifi,
  ShoppingBag,
  Store,
  CreditCard, 
  Globe, 
  Lock, 
  MessageSquare,
  Sun,
  Moon,
  Monitor,
  Settings,
  ChevronDown,
  Menu,
  X,
  User,
  Search,
  Bell,
  Copy,
  Check,
  Key,
  ExternalLink,
  LogIn,
  AlertCircle
} from 'lucide-react';


import { useNavigate, useLocation, Link } from 'react-router-dom';

import { HELP_CATEGORIES, enableCcai } from './utils/constants.js';
import AppRoutes from './AppRoutes.jsx';
import { SettingsProvider, useSettings } from './context/SettingsContext.jsx';
import {
  getMessages,
  registerDeviceToken,
  unregisterDeviceToken,
  uploadFileToGcs,
  uploadAndValidateArtifact,
  getCxasAuthToken,
  getCustomerProfile,
  getCcaiAuthToken,
  getAccountsSummary
} from './utils/api.js';
import GoogleCloudIcon from './components/GoogleCloudIcon.jsx';
import GcpInfoModal from './components/GcpInfoModal.jsx';



const IconMap = {
  Shield: Shield,
  Globe: Globe,
  Lock: Lock,
  CreditCard: CreditCard,
  Heart: Heart,
  Activity: Activity,
  Phone: Phone,
  Wifi: Wifi,
  ShoppingBag: ShoppingBag,
  Store: Store
};

const kebabCase = (str) => str.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();

// Securely mask PII data to prevent sensitive data exposure in the UI
const maskEmail = (email) => {
  if (!email) return 'N/A';
  const parts = email.split('@');
  if (parts.length !== 2) return '***';
  const [name, domain] = parts;
  const maskedName = name.length > 2 ? `${name.slice(0, 2)}***` : `${name.slice(0, 1)}***`;
  return `${maskedName}@${domain}`;
};

const maskPhone = (phone) => {
  if (!phone) return 'N/A';
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length >= 4) {
    return `***-***-${cleaned.slice(-4)}`;
  }
  return '***-***-****';
};

const getInitials = (profile) => {
  if (!profile) return '';
  const f = profile.first_name ? profile.first_name.charAt(0).toUpperCase() : '';
  const l = profile.last_name ? profile.last_name.charAt(0).toUpperCase() : '';
  return (f + l) || 'C';
};

const getCesAppUrl = (path) => {
  if (!path) return '';
  const parts = path.split('/');
  const projectIdx = parts.indexOf('projects');
  const locationIdx = parts.indexOf('locations');
  const appIdx = parts.indexOf('apps');
  
  if (projectIdx !== -1 && locationIdx !== -1 && appIdx !== -1) {
    const proj = parts[projectIdx + 1];
    const loc = parts[locationIdx + 1];
    const app = parts[appIdx + 1];
    return `https://ces.cloud.google.com/projects/${proj}/locations/${loc}/apps/${app}`;
  }
  return '';
};

function AppContent() {
  const navigate = useNavigate();
  const location = useLocation();
  const isSearchPage = location.pathname === '/search';
  const { 
    theme, setTheme,
    isCxAgentEnabled,
    isCcaiAgentEnabled,
    bankName,
    siteTitle,
    footerText,
    logoIcon,
    customLogoUrl,
    logoFit,
    brandColorFrom,
    brandColorTo,
    isExportModalOpen, setIsExportModalOpen,
    resolvedTheme,
    handleExport
  } = useSettings();

  const [loanAmount, setLoanAmount] = useState(25000);
  const [loanTerm, setLoanTerm] = useState(60);
  const [activeBot, setActiveBot] = useState(null);

  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isGcpInfoModalOpen, setIsGcpInfoModalOpen] = useState(false);
  const [isAuthInfoModalOpen, setIsAuthInfoModalOpen] = useState(false);
  const [isGcpEnvModalOpen, setIsGcpEnvModalOpen] = useState(false);
  const [copiedField, setCopiedField] = useState(null);
  const projectId = window.firebaseConfig?.projectId;
  const cxParts = (window.env?.CX_AGENT_STUDIO_DEPLOYMENT_NAME || '').split('/');
  const cxProjectId = cxParts.includes('projects') ? cxParts[cxParts.indexOf('projects') + 1] : '';
  const appId = cxParts.includes('apps') ? cxParts[cxParts.indexOf('apps') + 1] : '';

  const handleCopy = (text, field) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 1500);
  };

  const [isAltPressed, setIsAltPressed] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Alt') {
        setIsAltPressed(true);
      }
    };
    const handleKeyUp = (e) => {
      if (e.key === 'Alt') {
        setIsAltPressed(false);
      }
    };
    const handleBlur = () => {
      setIsAltPressed(false);
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('blur', handleBlur);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('blur', handleBlur);
    };
  }, []);

  const handleCopyNewToken = async () => {
    if (!fbUser) return;
    try {
      const token = await fbUser.getIdToken(true);
      navigator.clipboard.writeText(token);
      setCopiedField('token');
      setTimeout(() => setCopiedField(null), 1500);
      console.log("Refreshed Firebase ID token copied to clipboard successfully!");
    } catch (err) {
      console.error("Failed to refresh or copy Firebase ID token:", err);
    }
  };

  const [isReady, setIsReady] = useState(false);
  const [isChatSdkReady, setIsChatSdkReady] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [customerProfile, setCustomerProfile] = useState(null);
  const [activeNotification, setActiveNotification] = useState(null);
  const [fcmToken, setFcmToken] = useState(null);
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationPermission, setNotificationPermission] = useState(
    typeof Notification === 'undefined' ? 'unsupported' : Notification.permission
  );
  const [fbUser, setFbUser] = useState(null);

  useEffect(() => {
    // Scroll to top on route change
    window.scrollTo(0, 0);
    setIsProfileOpen(false);

    // Update page title dynamically
    const pageTitles = {
      '/': siteTitle,
      '/checking-accounts': `Checking Accounts | ${bankName}`,
      '/savings-accounts': `Savings Accounts | ${bankName}`,
      '/certificate-accounts': `Certificate Accounts | ${bankName}`,
      '/credit-cards': `Credit Cards | ${bankName}`,
      '/mortgages': `Mortgages & Home Loans | ${bankName}`,
      '/mortgage-rates': `Mortgage Rates | ${bankName}`,
      '/help-center': `Help & Learning Center | ${bankName}`,
      '/fee-schedule': `Fee Schedule | ${bankName}`,
      '/disclosures': `Account Disclosures | ${bankName}`,
      '/settings': `Settings | ${bankName}`,
      '/edit-profile': `Edit Profile | ${bankName}`,
      '/apply/credit-card': `Apply for Credit Card | ${bankName}`,
      '/search': `Search Site | ${bankName}`,
      '/support/voice': `Voice Support Consultation | ${bankName}`,
      '/locator': `Find Branch/ATM | ${bankName}`,
    };

    const title = pageTitles[location.pathname] || `${bankName} | Premium Digital Banking`;
    document.title = title;
  }, [location.pathname, bankName, siteTitle]);

  const fetchUnreadCount = useCallback(async () => {
    if (!window.firebaseAuth?.getCurrentUser()) return;
    try {
      const messages = await getMessages();
      const count = messages.filter((msg) => msg.sender !== 'user' && !msg.is_user_read).length;
      setUnreadCount(count);
    } catch (err) {
      console.error("Failed to fetch unread messages count:", err);
    }
  }, [setUnreadCount]);

  useEffect(() => {
    if (fbUser) {
      fetchUnreadCount();
      const interval = setInterval(fetchUnreadCount, 15000);
      return () => clearInterval(interval);
    }
  }, [fbUser, fetchUnreadCount]);

  useEffect(() => {
    const handleRefreshUnread = () => {
      fetchUnreadCount();
    };
    window.addEventListener('refresh-unread-count', handleRefreshUnread);
    return () => window.removeEventListener('refresh-unread-count', handleRefreshUnread);
  }, [fetchUnreadCount]);

  const [accountsSummary, setAccountsSummary] = useState(null);

  const fetchAccountsSummary = useCallback(async () => {
    if (!window.firebaseAuth?.getCurrentUser()) return;
    try {
      const summary = await getAccountsSummary();
      setAccountsSummary(summary);
    } catch (err) {
      console.error("Failed to load accounts summary for navigation dropdown:", err);
    }
  }, []);

  useEffect(() => {
    if (fbUser) {
      fetchAccountsSummary();
    } else {
      setAccountsSummary(null);
    }
  }, [fbUser, location.pathname, fetchAccountsSummary]);

  useEffect(() => {
    const isSupportMessageForCurrentUser = (data = {}) => {
      const notificationUserId = data.user_id;
      const currentUserId = customerProfile?.user_id || fbUser?.uid;
      return data.type === 'support_message' && (!notificationUserId || notificationUserId === currentUserId);
    };

    const handleNotification = (e) => {
      console.log("Received custom push notification event:", e.detail);
      const payload = e.detail;
      if (payload && (payload.notification || payload.data)) {
        const isSupportMessage = isSupportMessageForCurrentUser(payload.data)
          && payload.data.title
          && payload.data.body;

        const isBroadcastAnnoucement = payload.data?.type === 'broadcast_announcement'
          && payload.data.title && payload.data.body;

        if (isSupportMessage || isBroadcastAnnoucement) {
          setActiveNotification({
            title: payload.data?.title,
            body: payload.data?.body,
            receivedAt: new Date(),
            data: payload.data
          });
        } else {
          console.log("Silent topic message or message without visual content received");
        }
        if (isSupportMessageForCurrentUser(payload.data)) {
          setUnreadCount(prev => prev + 1);
          fetchUnreadCount();
        }
      }
    };
    const handleSecureMessageCreated = (e) => {
      const data = e.detail || {};
      if (isSupportMessageForCurrentUser({ type: 'support_message', user_id: data.user_id })) {
        fetchUnreadCount();
      }
    };
    window.addEventListener('firebase-push-notification', handleNotification);
    window.addEventListener('secure-message-created', handleSecureMessageCreated);
    return () => {
      window.removeEventListener('firebase-push-notification', handleNotification);
      window.removeEventListener('secure-message-created', handleSecureMessageCreated);
    };
  }, [fetchUnreadCount, customerProfile, fbUser]);



  useEffect(() => {
    const handleToken = (e) => {
      const token = e.detail;
      setFcmToken(token);
    };
    window.addEventListener('firebase-token-retrieved', handleToken);
    return () => window.removeEventListener('firebase-token-retrieved', handleToken);
  }, []);

  useEffect(() => {
    const registerDevice = async () => {
      if (fbUser && fcmToken) {
        // Leave off allows us to subscribe additional topics on backend if required
        // if (localStorage.getItem('registered_fcm_token') === fcmToken) {
        //   console.log("Device token already registered in this browser.");
        //   return;
        // }

        try {
          await registerDeviceToken(fcmToken);
          console.log("Device token registered with backend successfully");
          localStorage.setItem('registered_fcm_token', fcmToken);
        } catch (err) {
          console.error("Error registering device token:", err);
        }
      }
    };
    registerDevice();
  }, [fbUser, fcmToken]);

  useEffect(() => {
    if (!fbUser) return;

    if ('permissions' in navigator) {
      let permissionStatusObj = null;

      const handlePermissionChange = async () => {
        if (permissionStatusObj) {
          const state = permissionStatusObj.state;
          console.log("Notification permission state changed:", state);
          setNotificationPermission(state);
          if (state === 'denied' || state === 'prompt') {
            const registeredToken = localStorage.getItem('registered_fcm_token');
            if (registeredToken) {
              console.log("Permission revoked/reset. Unregistering FCM token.");
              try {
                await unregisterDeviceToken(registeredToken);
                console.log("FCM token unregistered from backend successfully.");
                localStorage.removeItem('registered_fcm_token');
                setFcmToken(null);
              } catch (err) {
                console.error("Error unregistering FCM token:", err);
              }
            }
          }
        }
      };

      navigator.permissions.query({ name: 'notifications' }).then((status) => {
        permissionStatusObj = status;
        setNotificationPermission(status.state);
        status.addEventListener('change', handlePermissionChange);
      }).catch(err => {
        console.warn("Permissions API query for notifications not supported or failed:", err);
      });

      return () => {
        if (permissionStatusObj) {
          permissionStatusObj.removeEventListener('change', handlePermissionChange);
        }
      };
    }
  }, [fbUser]);

  const handleEnableNotifications = async () => {
    if (!window.firebaseNotifications?.requestPermission) return;
    await window.firebaseNotifications.requestPermission();
    setNotificationPermission(window.firebaseNotifications.getPermissionState?.() || Notification.permission);
  };


  const userDataRef = useRef({ email: null, sub: null });
  const isFetchingRef = useRef(false);
  const messengerNodeRef = useRef(null);
  const customerProfileRef = useRef(null);
  const chatSessionInitializedRef = useRef(false);
  const ccaasInstanceRef = useRef(null);

  useEffect(() => {
    customerProfileRef.current = customerProfile;
  }, [customerProfile]);



  useEffect(() => {
    const applyTheme = (t) => {
      const resolvedTheme = t === 'dark' || (t === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';

      if (resolvedTheme === 'dark') {
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
      }

      if (messengerNodeRef.current) {
        messengerNodeRef.current.setAttribute('color-scheme', resolvedTheme);
      }
    };

    applyTheme(theme);
    localStorage.setItem('theme', theme);

    if (theme === 'auto') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      const handleChange = () => applyTheme('auto');
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    }
  }, [theme]);


  const interestRate = 5.49;

  const messengerRefCallback = useCallback((node) => {
    if (node !== null) {
      console.log("chat-messenger element mounted via callback ref");
      messengerNodeRef.current = node;

      const handleLoaded = (event) => {
        console.log("chat-messenger-loaded event fired in callback ref:", event);

        const toolName = window.env?.CX_AGENT_STUDIO_UPLOAD_TOOL_NAME;
        const toolId = toolName?.split('/').pop();

        console.log("Registered upload tool: ", toolName);

        if (!toolName || !toolId) {
          console.error('CX_AGENT_STUDIO_UPLOAD_TOOL_NAME not configured. Please add it to public/config.js');
          return;
        }

        node.registerClientSideFunction(
          toolName,
          toolId,
          (args) => {
            console.log('executing function with arguments', { args });
            const mimeType = args.mime_type || 'application/pdf';

            return new Promise((resolve) => {
              const input = document.createElement('input');
              input.type = 'file';
              input.accept = mimeType;
              input.onchange = async (e) => {
                const file = e.target.files[0];
                if (!file) {
                  resolve({ status: 'cancelled' });
                  return;
                }

                try {
                  const useGCS = false; // args.USE_GCS !== undefined ? args.USE_GCS : true;

                  if (useGCS) {
                    // Use the signed URL provided in args
                    const signed_url = args.signed_url;

                    if (!signed_url) {
                      throw new Error('No signed URL provided in arguments');
                    }

                    // 2. Upload file to GCS using PUT
                    await uploadFileToGcs(signed_url, file, mimeType);

                    resolve({ status: 'success' });
                  } else {
                    // Create a separate request that invokes the /upload-and-validate endpoint
                    const reader = new FileReader();
                    reader.onload = async () => {
                      const base64Content = reader.result.split(',')[1];

                      try {
                        const result = await uploadAndValidateArtifact({
                          application_id: args.application_id,
                          artifact_type: args.artifact_type || "W2",
                          base64_content: base64Content,
                          content_type: file.type || mimeType
                        });

                        resolve({ status: 'success', data: result });
                      } catch (error) {
                        console.error('Upload failed', error);
                        resolve({ status: 'error', message: error.message });
                      }
                    };
                    reader.readAsDataURL(file);
                  }
                } catch (error) {
                  console.error('Upload failed', error);
                  resolve({ status: 'error', message: error.message });
                }
              };
              input.click();
            });
          },
        );

        const populateToolName = window.env?.CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME;
        const populateToolId = populateToolName?.split('/').pop();

        console.log("Registered populate content form tool: ", populateToolName);

        if (populateToolName && populateToolId) {
          node.registerClientSideFunction(
            populateToolName,
            populateToolId,
            (args) => {
              console.log('executing populate form function with arguments', { args });

              // Map product name to URL param format (e.g. "Equinox Horizon" -> "equinox-horizon")
              const cardParam = args.product ? args.product.toLowerCase().replace(/\s+/g, '-') : 'aura-elite-reserve';

              // Close chat window so user can see the form
              // setIsChatOpen(false);

              // Navigate using React Router state
              navigate(`/apply/credit-card?card=${cardParam}`, { state: { prefill: args } });

              return Promise.resolve({ status: 'success' });
            }
          );
        }

        const locationToolName = window.env?.CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME;
        const locationToolId = locationToolName?.split('/').pop();

        console.log("Registered get user location tool: ", locationToolName);

        if (locationToolName && locationToolId) {
          node.registerClientSideFunction(
            locationToolName,
            locationToolId,
            (args) => {
              console.log('executing get user location function with arguments', { args });

              return new Promise((resolve) => {
                if (!navigator.geolocation) {
                  console.warn("Geolocation is not supported by this browser.");
                  resolve(null);
                  return;
                }

                navigator.geolocation.getCurrentPosition(
                  (position) => {
                    console.log("Current position retrieved:", position.coords.latitude, position.coords.longitude);
                    resolve({
                      latitude: position.coords.latitude,
                      longitude: position.coords.longitude
                    });
                  },
                  (error) => {
                    console.warn("Error getting user location or permission denied:", error);
                    resolve(null);
                  }
                );
              });
            }
          );
        }

        const injectDataAndGreet = async () => {
          console.log("injectDataAndGreet called");
          if (typeof node.setVariables === 'function') {
            const profile = customerProfileRef.current;
            if (!profile) {
              console.log("⚠️ Profile not ready yet. Skipping variable injection.");
              return;
            }
            console.log("customer profile: ", profile);

            const customerEmail = profile?.email;
            const userId = profile?.user_id;
            const firstName = profile?.first_name;
            const lastName = profile?.last_name;
            const phoneNumber = profile?.phone_number;
            const customerName = (firstName || lastName)
              ? `${firstName || ''} ${lastName || ''}`.trim()
              : customerEmail;

            let cxas_token = window.cxasToken;
            if (!cxas_token) {
              try {
                const data = await getCxasAuthToken();
                cxas_token = data.token;
              } catch (err) {
                console.error("Error fetching CXAS token:", err);
              }
            }

            let custDict = {
              is_ujet_sdk: false,
              email: customerEmail,
              user_id: userId,
              first_name: firstName,
              last_name: lastName,
              phone_number: phoneNumber,
              customer_name: customerName,
              access_token: `Bearer ${cxas_token}`
            };

            node.setVariables(custDict);
            console.log("setVariables invoked with:", custDict);

            setTimeout(() => {
              console.log("🗣️ Triggering initial agent greeting...");
              node.sendQuery("Hello");
            }, 500);
          }
        };

        // Examples:
        // https://paste.googleplex.com/5282104721145856
        // https://codeplay.googleplex.com/playground/call-me-maybe/1
        // https://codeplay.googleplex.com/playground/call-me-maybe/2

        // if (!sessionStorage.getItem("chatAgentInitialized")) {
        //   console.log("chatAgentInitialized not set, injecting data and greeting...");
        //   injectDataAndGreet();
        //   sessionStorage.setItem("chatAgentInitialized", "true");
        // }

        const originalStartNewSession = node.startNewSession;
        if (typeof originalStartNewSession === 'function') {
          node.startNewSession = async function () {
            console.log("♻️ Resetting session...");
            await originalStartNewSession.call(this);

            await injectDataAndGreet();
            console.log("✅ Session restarted & variables injected!");
          };
        }

        // Fixes issue where the variables are not set in time for the initial load
        // node.startNewSession();
        if (!chatSessionInitializedRef.current) {
          console.log("chatAgentInitialized not set, injecting data and greeting...");
        // injectDataAndGreet();
          node.startNewSession();
          chatSessionInitializedRef.current = true;
        }
      };

      node.addEventListener('chat-messenger-loaded', handleLoaded);
      console.log("chat-messenger-loaded listener added in callback ref");
      
      node._handleLoaded = handleLoaded;
    } else {
      console.log("chat-messenger element unmounted via callback ref");
      if (messengerNodeRef.current && messengerNodeRef.current._handleLoaded) {
        messengerNodeRef.current.removeEventListener('chat-messenger-loaded', messengerNodeRef.current._handleLoaded);
        console.log("chat-messenger-loaded listener removed in callback ref");
      }
      messengerNodeRef.current = null;
    }
  }, [navigate]);

  const initializeFirebaseSession = async (user) => {
    try {
      userDataRef.current = { email: user.email, sub: user.uid };

      const profileData = await getCustomerProfile();
      if (profileData && profileData.user_id) {
        setCustomerProfile(profileData);
        customerProfileRef.current = profileData;

        // Proactively fetch and cache CXAS token to eliminate async race condition on widget mount
        try {
          const data = await getCxasAuthToken();
          window.cxasToken = data.token;
        } catch (tokenErr) {
          console.error("Proactive CXAS token fetch failed:", tokenErr);
        }

        // Proactively restart chat session with newly loaded profile variables to resolve page reload race conditions
        const messengerNode = document.querySelector('df-messenger') || document.querySelector('chat-messenger');
        if (messengerNode && typeof messengerNode.startNewSession === 'function') {
          console.log("🔄 Re-initializing chat session with newly loaded profile context...");
          messengerNode.startNewSession();
          chatSessionInitializedRef.current = true;
        }
      }
      setIsReady(true);
    } catch (err) {
      console.error("Failed to initialize session with Firebase token:", err);
      setIsReady(true);
    }
  };

  useEffect(() => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;

    const setupAuthListener = () => {
      // Only process redirect results when deployed (non-localhost)
      if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
        if (typeof window.firebaseAuth.getRedirectResult === 'function') {
          window.firebaseAuth.getRedirectResult()
            .then((result) => {
              if (result) {
                console.log("Redirect sign-in success:", result.user);
              }
            })
            .catch((error) => {
              console.error("Redirect sign-in error:", error);
            });
        }
      }

      window.firebaseAuth.onAuthStateChanged(async (user) => {
        if (user) {
          setFbUser(user);
          await initializeFirebaseSession(user);
        } else {
          setFbUser(null);
          setCustomerProfile(null);
          customerProfileRef.current = null;
          window.cxasToken = null;
          chatSessionInitializedRef.current = false;
          setIsReady(true);
        }
      });
    };

    if (window.firebaseAuth) {
      setupAuthListener();
    } else {
      const handleAuthReady = () => {
        setupAuthListener();
      };
      window.addEventListener('firebase-auth-ready', handleAuthReady);
      return () => window.removeEventListener('firebase-auth-ready', handleAuthReady);
    }
  }, []);

  useEffect(() => {
    // Load Dialogflow CX Messenger dynamically
    const initializeChat = () => {
      if (window.chatSdk && window.env?.CX_AGENT_STUDIO_DEPLOYMENT_NAME) {
        if (window.chatContextRegistered) {
          console.log("Dialogflow CX Messenger context already registered, skipping duplicate registration.");
          setIsChatSdkReady(true);
          return;
        }
        window.chatSdk.registerContext(
          window.chatSdk.prebuilts.ces.createContext({
            deploymentName: window.env.CX_AGENT_STUDIO_DEPLOYMENT_NAME,
            tokenBroker: {
              enableTokenBroker: true,
              enableRecaptcha: false
            },
            enableWelcomeEvent: false
          })
        );
        window.chatContextRegistered = true;
        console.log("Dialogflow CX Messenger initialized dynamically.");
        setIsChatSdkReady(true);
      }
    };

    const scriptId = 'dialogflow-messenger-script';
    if (!document.getElementById(scriptId)) {
      const script = document.createElement('script');
      script.id = scriptId;
      script.src = "https://www.gstatic.com/chat-messenger/sdk/prod/v1.16/chat-messenger.js";
      script.async = true;

      script.onload = () => {
        initializeChat();
      };

      document.head.appendChild(script);

      window.addEventListener("chat-messenger-loaded", initializeChat);
      return () => {
        window.removeEventListener("chat-messenger-loaded", initializeChat);
      };
    } else {
      if (window.chatSdk) {
        initializeChat();
      } else {
        const checkChatSdkLoaded = () => {
          if (window.chatSdk) {
            initializeChat();
            window.removeEventListener("chat-messenger-loaded", checkChatSdkLoaded);
          }
        };
        window.addEventListener("chat-messenger-loaded", checkChatSdkLoaded);
        return () => window.removeEventListener("chat-messenger-loaded", checkChatSdkLoaded);
      }
    }
  }, []);

  useEffect(() => {
    const widget = document.getElementById('ccaas-widget');
    if (widget) {
      widget.style.display = (isCcaiAgentEnabled && fbUser && enableCcai()) ? 'block' : 'none';
    }
  }, [isCcaiAgentEnabled, fbUser]);

  useEffect(() => {
    const cleanUpUjet = () => {
      if (ccaasInstanceRef.current) {
        if (typeof ccaasInstanceRef.current.destroy === 'function') {
          try {
            ccaasInstanceRef.current.destroy();
          } catch (e) {
            console.warn("Error calling ccaas.destroy:", e);
          }
        } else if (typeof ccaasInstanceRef.current.unmount === 'function') {
          try {
            ccaasInstanceRef.current.unmount();
          } catch (e) {
            console.warn("Error calling ccaas.unmount:", e);
          }
        }
        ccaasInstanceRef.current = null;
      }
      const widget = document.getElementById('ccaas-widget');
      if (widget) {
        widget.innerHTML = '';
      }
    };

    if (!fbUser || !customerProfile || !isCcaiAgentEnabled || !enableCcai()) {
      cleanUpUjet();
      return;
    }

    const host = window.env?.CCAI_HOST || import.meta.env.VITE_CCAI_HOST;
    const companyId = window.env?.CCAI_COMPANY_ID || import.meta.env.VITE_CCAI_COMPANY_ID;

    const initUjet = async () => {
      // Prevent double mounting if already mounted
      if (ccaasInstanceRef.current) {
        console.log("UJET widget already initialized, skipping mounting.");
        return;
      }

      const customerEmail = customerProfile?.email;
      const userId = customerProfile?.user_id;
      const firstName = customerProfile?.first_name;
      const lastName = customerProfile?.last_name;
      const phoneNumber = customerProfile?.phone_number;
      const customerName = (firstName || lastName)
        ? `${firstName || ''} ${lastName || ''}`.trim()
        : customerEmail;

      let cxas_token = window.cxasToken;
      if (!cxas_token) {
        try {
          const data = await getCxasAuthToken();
          cxas_token = data.token;
        } catch (err) {
          console.error("Error fetching CXAS token:", err);
        }
      }

      const ccaas = new window.UJET({
        companyId: companyId,
        host: host,
        authenticate: async () => {
          try {
            const data = await getCcaiAuthToken();
            return { token: data.token };
          } catch (error) {
            console.error("Failed to authenticate with chat service:", error);
            return { token: null };
          }
        }
      });

      ccaas.config({
        menuKey: "mortgage_bot",
        accent: "green",
        customData: {
          is_ujet_sdk: {
            label: "Is UJET SDK",
            value: true
          },
          email: {
            label: "Email",
            value: customerEmail
          },
          user_id: {
            label: "User ID",
            value: userId
          },
          first_name: {
            label: "First Name",
            value: firstName
          },
          last_name: {
            label: "Last Name",
            value: lastName
          },
          phone_number: {
            label: "Phone Number",
            value: phoneNumber
          },
          customer_name: {
            label: "Customer Name",
            value: customerName
          },
          access_token: {
            label: "Access Token",
            value: cxas_token ? `Bearer ${cxas_token}` : null
          }
        }
      });
      ccaas.mount("#ccaas-widget");
      ccaasInstanceRef.current = ccaas;
    };

    if (window.UJET) {
      initUjet();
    } else if (!document.getElementById('ccaas-widget-script')) {
      // Load CCAI Web SDK v3 dynamically
      const script = document.createElement('script');
      script.id = 'ccaas-widget-script';
      script.src = `${host}/web-sdk/v3/widget.js`;
      script.onload = () => {
        if (window.UJET) {
          initUjet();
        }
      };
      document.head.appendChild(script);
    }

    return () => {
      cleanUpUjet();
    };
  }, [fbUser, customerProfile, isCcaiAgentEnabled]);


  const calculateMonthlyPayment = () => {
    const p = loanAmount;
    const r = interestRate / 100 / 12;
    const n = loanTerm;
    const monthly = (p * r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1);
    return monthly.toFixed(2);
  };

  const getFooterLinkClass = (path) => {
    const isActive = location.pathname === path;
    return `transition-colors cursor-pointer ${
      isActive 
        ? 'text-emerald-600 dark:text-emerald-400 font-semibold' 
        : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
    }`;
  };

  const resolvedIconUrl = customLogoUrl || (logoIcon ? `https://unpkg.com/lucide-static@latest/icons/${kebabCase(logoIcon)}.svg` : "/favicon.svg");

  const checkingAccs = accountsSummary?.deposit_accounts?.filter(a => a.account_type === 'CHECKING') || [];
  const savingsAccs = accountsSummary?.deposit_accounts?.filter(a => a.account_type === 'SAVINGS') || [];
  const creditAccs = accountsSummary?.credit_accounts || [];

  const stableEnvUrl = window.env?.STABLE_ENV_URL;
  const feedbackUrl = window.env?.FEEDBACK_URL;
  const showStableBanner = stableEnvUrl && (() => {
    try {
      const stableHost = new URL(stableEnvUrl.startsWith('http') ? stableEnvUrl : `http://${stableEnvUrl}`).hostname;
      return stableHost !== window.location.hostname;
    } catch {
      return stableEnvUrl !== window.location.hostname;
    }
  })();
  const isStableEnv = stableEnvUrl && !showStableBanner && feedbackUrl;

  return (
    <div 
      className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 font-[Outfit] antialiased overflow-x-hidden"
      style={{ paddingTop: (showStableBanner || isStableEnv) ? '36px' : '0px' }}
    >
      {showStableBanner && (
        <div className="fixed top-0 left-0 right-0 h-9 z-50 bg-amber-500/10 dark:bg-amber-500/5 border-b border-amber-500/20 text-amber-800 dark:text-amber-300 text-xs flex items-center justify-center font-medium gap-1.5 px-4 backdrop-blur-md">
          <AlertCircle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 shrink-0" />
          <span>This is a test environment. For the stable environment go to</span>
          <a href={stableEnvUrl} target="_blank" rel="noopener noreferrer" className="underline hover:text-amber-950 dark:hover:text-amber-100 transition-colors font-semibold flex items-center gap-0.5">
            {stableEnvUrl}
            <ExternalLink className="w-3 h-3 inline" />
          </a>
        </div>
      )}
      {isStableEnv && (
        <div className="fixed top-0 left-0 right-0 h-9 z-50 bg-emerald-500/10 dark:bg-emerald-500/5 border-b border-emerald-500/20 text-emerald-800 dark:text-emerald-300 text-xs flex items-center justify-center font-medium gap-1.5 px-4 backdrop-blur-md">
          <MessageSquare className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
          <span>Please submit feedback or issues to</span>
          <a href={feedbackUrl} target="_blank" rel="noopener noreferrer" className="underline hover:text-emerald-950 dark:hover:text-emerald-100 transition-colors font-semibold flex items-center gap-0.5">
            Google Buganizer
            <ExternalLink className="w-3 h-3 inline" />
          </a>
        </div>
      )}
      {/* Navigation */}
      <nav 
        className="fixed left-0 right-0 z-50 bg-white/80 dark:bg-slate-950/80 backdrop-blur-xl border-b border-slate-200 dark:border-slate-800/50"
        style={{ top: (showStableBanner || isStableEnv) ? '36px' : '0px' }}
      >
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between gap-4">
          <div className="flex items-center space-x-8 lg:space-x-12">
            <Link
              to="/"
              className="flex items-center space-x-3 cursor-pointer"
            >
              <div 
                className={customLogoUrl ? "w-10 h-10 flex items-center justify-center" : "w-10 h-10 rounded-xl flex items-center justify-center shadow-lg"}
                style={customLogoUrl ? {} : { backgroundImage: `linear-gradient(to top right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 10px 15px -3px ${brandColorFrom}33` }}
              >
                {customLogoUrl ? (
                  <img src={customLogoUrl} alt="Logo" className={`w-full h-full object-${logoFit}`} />
                ) : (() => {
                  const Logo = IconMap[logoIcon] || Shield;
                  return <Logo className="w-6 h-6 text-slate-950" />;
                })()}
              </div>
              <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-slate-900 via-slate-700 to-slate-500 dark:from-white dark:via-slate-200 dark:to-slate-400 bg-clip-text text-transparent">
                {bankName}
              </span>
            </Link>
            
            <div className="hidden md:flex items-center space-x-8 text-sm font-medium text-slate-600 dark:text-slate-300">
              <Link to="/" className={`hover:text-slate-900 dark:hover:text-white transition-colors cursor-pointer ${location.pathname === '/' ? 'text-slate-900 dark:text-white font-bold' : ''}`}>Home</Link>
              
              {fbUser && (
                <div className="relative group py-2">
                  <Link to="/accounts" className={`hover:text-slate-900 dark:hover:text-white transition-colors flex items-center gap-1 cursor-pointer ${location.pathname === '/accounts' ? 'text-emerald-600 dark:text-emerald-400 font-bold' : ''}`}>
                    <span>Accounts</span>
                    <ChevronDown className="w-3.5 h-3.5 transition-transform duration-300 group-hover:rotate-180" />
                  </Link>

                  {/* Dropdown panel */}
                  {accountsSummary && (checkingAccs.length > 0 || savingsAccs.length > 0 || creditAccs.length > 0) && (
                    <div className="absolute left-0 top-full mt-1 w-64 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-3 shadow-2xl opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-all duration-300 translate-y-2 group-hover:translate-y-0 z-50">
                      {checkingAccs.length > 0 && (
                        <>
                          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5">Checking</div>
                          {checkingAccs.map(acc => (
                            <Link 
                              key={acc.account_id}
                              to={`/accounts?id=${acc.account_id}&type=checking`} 
                              className="w-full text-left px-3 py-2 rounded-xl text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-semibold block truncate"
                            >
                              {acc.product_name}
                            </Link>
                          ))}
                        </>
                      )}
                      
                      {savingsAccs.length > 0 && (
                        <>
                          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5 mt-2 border-t border-slate-100 dark:border-slate-800/60 pt-2">Savings</div>
                          {savingsAccs.map(acc => (
                            <Link 
                              key={acc.account_id}
                              to={`/accounts?id=${acc.account_id}&type=savings`} 
                              className="w-full text-left px-3 py-2 rounded-xl text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-semibold block truncate"
                            >
                              {acc.product_name}
                            </Link>
                          ))}
                        </>
                      )}

                      {creditAccs.length > 0 && (
                        <>
                          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5 mt-2 border-t border-slate-100 dark:border-slate-800/60 pt-2">Credit Cards</div>
                          {creditAccs.map(acc => (
                            <Link 
                              key={acc.account_id}
                              to={`/accounts?id=${acc.account_id}&type=credit`} 
                              className="w-full text-left px-3 py-2 rounded-xl text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-semibold block truncate"
                            >
                              {acc.product_name || "Nova Everyday Visa"}
                            </Link>
                          ))}
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}
              
              {/* Consolidated Products Menu with Mouseover Dropdown */}
              <div className="relative group py-2">
                <Link 
                  to="/compare-products"
                  className={`hover:text-slate-900 dark:hover:text-white transition-colors flex items-center gap-1 cursor-pointer ${['/checking-accounts', '/savings-accounts', '/certificate-accounts', '/credit-cards', '/mortgages', '/mortgage-rates', '/compare-products'].includes(location.pathname) ? 'text-emerald-600 dark:text-emerald-400 font-bold' : ''}`}
                >
                  <span>Products</span>
                  <ChevronDown className="w-3.5 h-3.5 transition-transform duration-300 group-hover:rotate-180" />
                </Link>

                {/* Dropdown panel */}
                <div className="absolute left-0 top-full mt-1 w-64 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-3 shadow-2xl opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-all duration-300 translate-y-2 group-hover:translate-y-0 z-50">
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5">Deposit Accounts</div>
                  <Link to="/checking-accounts" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                    <span>Checking</span>
                    {location.pathname === '/checking-accounts' && <div className="w-1.5 h-1.5 rounded-full bg-teal-500"></div>}
                  </Link>
                  <Link to="/savings-accounts" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                    <span>Savings</span>
                    {location.pathname === '/savings-accounts' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                  </Link>
                  <Link to="/certificate-accounts" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                    <span>Certificate Accounts</span>
                    {location.pathname === '/certificate-accounts' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                  </Link>
                  
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5 mt-2 border-t border-slate-100 dark:border-slate-800 pt-2">Credit & Cards</div>
                  <Link to="/credit-cards" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                    <span>Credit Cards</span>
                    {location.pathname === '/credit-cards' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                  </Link>


                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5 mt-2 border-t border-slate-100 dark:border-slate-800 pt-2">Home Financing</div>
                  <Link to="/mortgages" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                    <span>Mortgages</span>
                    {location.pathname === '/mortgages' && <div className="w-1.5 h-1.5 rounded-full bg-cyan-500"></div>}
                  </Link>
                  <Link to="/mortgage-rates" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                    <span>Mortgage Rates</span>
                    {location.pathname === '/mortgage-rates' && <div className="w-1.5 h-1.5 rounded-full bg-cyan-500"></div>}
                  </Link>

                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5 mt-2 border-t border-slate-100 dark:border-slate-800 pt-2">Product Tools</div>
                  <Link to="/compare-products" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                    <span>Compare Products</span>
                    {location.pathname === '/compare-products' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                  </Link>
                </div>
              </div>

              {/* Help Center Menu with Mouseover Dropdown */}
              <div className="relative group py-2">
                <Link to="/help-center" state={{ category: 'All' }} className={`hover:text-slate-900 dark:hover:text-white transition-colors flex items-center gap-1 cursor-pointer ${['/help-center', '/fee-schedule', '/disclosures', '/locator', '/support/voice', '/secure-messaging'].includes(location.pathname) ? 'text-emerald-600 dark:text-emerald-400 font-bold' : ''}`}>
                  <span>Help Center</span>
                  <ChevronDown className="w-3.5 h-3.5 transition-transform duration-300 group-hover:rotate-180" />
                </Link>

                {/* Dropdown panel */}
                <div className="absolute left-0 top-full mt-1 w-64 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-3 shadow-2xl opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-all duration-300 translate-y-2 group-hover:translate-y-0 z-50">
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5">Knowledge Base</div>
                  <Link to="/help-center" state={{ category: 'All' }} className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                    <span>All Topics</span>
                    {location.pathname === '/help-center' && (!location.state?.category || location.state?.category === 'All') && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                  </Link>

                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5 mt-2 border-t border-slate-100 dark:border-slate-800 pt-2">Filter Topics</div>
                  {HELP_CATEGORIES.filter(cat => cat !== 'All').map((cat) => (
                    <Link key={cat} to="/help-center" state={{ category: cat }} className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                      <span>{cat}</span>
                      {location.pathname === '/help-center' && location.state?.category === cat && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                    </Link>
                  ))}

                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5 mt-2 border-t border-slate-100 dark:border-slate-800 pt-2">Documentation</div>
                  <Link to="/fee-schedule" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                    <span>Fee Schedule</span>
                    {location.pathname === '/fee-schedule' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                  </Link>
                  <Link to="/disclosures" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                    <span>Disclosures</span>
                    {location.pathname === '/disclosures' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                  </Link>
                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5 mt-2 border-t border-slate-100 dark:border-slate-800 pt-2">Customer Service</div>
                  <Link to="/locator" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                    <span>Find Branch/ATM</span>
                    {location.pathname === '/locator' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                  </Link>
                  {fbUser && (
                    <Link to="/support/voice" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                      <span>Credit Card Support</span>
                      {location.pathname === '/support/voice' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                    </Link>
                  )}
                  {fbUser && (
                    <Link to="/secure-messaging" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                      <span>Secure Messages</span>
                      {location.pathname === '/secure-messaging' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                    </Link>
                  )}

                  {fbUser && (
                    <>
                      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-3 py-1.5 mt-2 border-t border-slate-100 dark:border-slate-800 pt-2">Admin</div>
                      <Link to="/admin" className="w-full text-left px-3 py-2 rounded-xl text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 font-medium flex items-center justify-between">
                        <span>Admin Portal</span>
                        {location.pathname === '/admin' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                      </Link>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Header Search Input centered in middle */}
          {fbUser && (
            <div className="relative hidden md:block flex-1 max-w-lg mx-6">
              <Search className="absolute left-3.5 top-2.5 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search site..."
                className="w-full pl-8 pr-4 py-1.5 text-xs rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-emerald-500/30 transition-all cursor-pointer shadow-sm hover:border-slate-300 dark:hover:border-slate-700"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.target.value.trim()) {
                    const query = e.target.value.trim();
                    e.target.value = ""; // Clear header input
                    navigate('/search', { state: { initialQuery: query } });
                  }
                }}
              />
            </div>
          )}

          <div className="flex items-center space-x-2 sm:space-x-4 shrink-0">
            {!fbUser && (
              <button
                onClick={() => window.firebaseAuth ? window.firebaseAuth.signInWithGoogle() : window.location.href = '/?gcp-iap-mode=CLEAR_LOGIN_COOKIE'}
                className="px-3 sm:px-4 text-xs sm:text-sm font-semibold rounded-full transition-all duration-300 hover:scale-105 active:scale-95 flex items-center justify-center gap-1.5 sm:gap-2 cursor-pointer shadow-sm border border-slate-200/80 dark:border-slate-800/80 bg-slate-50 dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-850 dark:text-slate-200 h-9"
                title="Sign In"
              >
                <LogIn className="w-3.5 h-3.5 sm:w-4 sm:h-4" style={{ color: brandColorFrom }} />
                <span className="hidden sm:inline">Sign In</span>
              </button>
            )}
            {customerProfile && (
              <div className="flex items-center space-x-3 sm:space-x-4">
                <div
                  className="relative group py-2"
                  onClick={() => setIsProfileOpen(!isProfileOpen)}
                  onMouseLeave={() => setIsProfileOpen(false)}
                >
                  <div
                    className="w-9 h-9 rounded-full flex items-center justify-center font-bold text-sm text-slate-950 cursor-pointer shadow-md hover:scale-105 transition-all duration-300 relative"
                    style={{ backgroundImage: fbUser?.photoURL ? 'none' : `linear-gradient(to top right, ${brandColorFrom}, ${brandColorTo})` }}
                  >
                    {fbUser?.photoURL ? (
                      <img src={fbUser.photoURL} alt="Profile" className="w-full h-full rounded-full object-cover" />
                    ) : (
                      getInitials(customerProfile)
                    )}
                    {unreadCount > 0 && (
                      <span className="absolute -top-1 -right-1 bg-red-500 text-white font-bold text-[9px] w-4 h-4 rounded-full flex items-center justify-center border border-white dark:border-slate-950 shadow-sm animate-pulse">
                        {unreadCount}
                      </span>
                    )}
                  </div>

                  {/* Hover Card Details */}
                  <div
                    className={`absolute right-0 top-full mt-1 w-88 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-4 shadow-2xl transition-all duration-300 translate-y-2 z-50 ${isProfileOpen
                      ? 'opacity-100 pointer-events-auto translate-y-0'
                      : 'opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto group-hover:translate-y-0'
                      }`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={() => setIsAuthInfoModalOpen(true)}
                      className="absolute top-3.5 right-3.5 p-1.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-all active:scale-95 cursor-pointer flex items-center justify-center border border-slate-200/60 dark:border-slate-800/60 bg-white dark:bg-slate-900 shadow-sm"
                      title="Firebase & Identity Platform Integration Info"
                    >
                      <GoogleCloudIcon className="w-4 h-4" />
                    </button>
                    <div className="flex items-center space-x-3 pb-3 border-b border-slate-100 dark:border-slate-800 pr-8">
                      <div
                        className="w-10 h-10 rounded-full flex items-center justify-center font-bold text-base text-slate-950 shrink-0"
                        style={{ backgroundImage: fbUser?.photoURL ? 'none' : `linear-gradient(to top right, ${brandColorFrom}, ${brandColorTo})` }}
                      >
                        {fbUser?.photoURL ? (
                          <img src={fbUser.photoURL} alt="Profile" className="w-full h-full rounded-full object-cover" />
                        ) : (
                          getInitials(customerProfile)
                        )}
                      </div>
                      <div className="overflow-hidden text-left">
                        <div className="text-sm font-bold text-slate-900 dark:text-white truncate">
                          {customerProfile.first_name || customerProfile.last_name ? `${customerProfile.first_name || ''} ${customerProfile.last_name || ''}`.trim() : 'Customer'}
                        </div>
                        <div className="text-xs text-slate-400 flex items-center gap-1 min-w-0">
                          <span className="font-mono text-[10px] select-all">ID: {customerProfile.user_id}</span>
                          <button 
                            onClick={() => handleCopy(customerProfile.user_id, 'id')}
                            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors p-0.5 cursor-pointer"
                            title="Copy Customer ID"
                          >
                            {copiedField === 'id' ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="pt-3 space-y-2 text-xs text-left">
                      <div className="flex justify-between items-center">
                        <span className="text-slate-500 dark:text-slate-400">Email:</span>
                        <div className="flex items-center gap-1 font-medium text-slate-700 dark:text-slate-300">
                          <span>{maskEmail(customerProfile.email)}</span>
                          <button 
                            onClick={() => handleCopy(customerProfile.email, 'email')}
                            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors p-0.5 cursor-pointer"
                            title="Copy Email"
                          >
                            {copiedField === 'email' ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                          </button>
                        </div>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-slate-500 dark:text-slate-400">Phone:</span>
                        <div className="flex items-center gap-1 font-medium text-slate-700 dark:text-slate-300">
                          <span>{maskPhone(customerProfile.phone_number)}</span>
                          <button 
                            onClick={() => handleCopy(customerProfile.phone_number, 'phone')}
                            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors p-0.5 cursor-pointer"
                            title="Copy Phone Number"
                          >
                            {copiedField === 'phone' ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="pt-3 mt-3 border-t border-slate-100 dark:border-slate-800 flex flex-col gap-2">
                      <div className="flex gap-2 w-full">
                        <Link
                          to="/secure-messaging"
                          className="flex-grow py-2 px-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-all text-xs font-medium flex items-center justify-center gap-1.5 cursor-pointer"
                        >
                          <MessageSquare className="w-3 h-3 text-slate-400" />
                          <span>Secure Messages</span>
                        </Link>
                        {notificationPermission !== 'granted' && (
                          <button
                            onClick={handleEnableNotifications}
                            disabled={notificationPermission === 'denied' || notificationPermission === 'unsupported'}
                            className="flex-grow py-2 px-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-all text-xs font-medium flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
                            title={notificationPermission === 'denied' ? 'Notifications are blocked in browser settings' : 'Enable browser push notifications'}
                          >
                            <Bell className="w-3 h-3 text-slate-400" />
                            <span>{notificationPermission === 'denied' ? 'Notifications Blocked' : 'Enable Alerts'}</span>
                          </button>
                        )}
                        {isAltPressed && (
                          <button
                            onClick={handleCopyNewToken}
                            className="flex-grow py-2 px-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 hover:bg-emerald-100 dark:hover:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400 transition-all text-xs font-medium flex items-center justify-center gap-1.5 cursor-pointer"
                            title="Refresh & Copy Firebase ID Token"
                          >
                            <Key className="w-3 h-3 text-emerald-500" />
                            <span>{copiedField === 'token' ? 'Copied!' : 'ID Token'}</span>
                          </button>
                        )}
                      </div>
                      <div className="flex gap-2">
                        <button 
                          onClick={async () => {
                            if (window.firebaseAuth) {
                              // 1. Wipe the local Firebase token on the app side
                              await window.firebaseAuth.signOut();
                            }

                            if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
                              // 2. Clear IAP cookies silently in the background
                              await fetch('/_gcp_iap/clear_login_cookie', { credentials: 'include' });

                              // 3. FORCE A HARD NETWORK RELOAD
                              // Passing 'true' forces the browser to bypass the cache and fetch from the server.
                              // This triggers the IAP redirect instantly!
                              window.location.reload(true);
                            } else {
                              window.location.reload();
                            }
                          }}
                          className="flex-grow py-2 px-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-all text-xs font-medium flex items-center justify-center gap-1.5 cursor-pointer"
                        >
                          <Lock className="w-3 h-3 text-slate-400" />
                          <span>{fbUser ? 'Sign Out' : 'Re-auth IAP'}</span>
                        </button>
                        <Link
                          to="/edit-profile"
                          className="flex-grow py-2 px-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-all text-xs font-medium flex items-center justify-center gap-1.5 cursor-pointer"
                        >
                          <User className="w-3 h-3 text-slate-400" />
                          <span>Edit Profile</span>
                        </Link>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <button
              onClick={() => setIsMobileMenuOpen(true)}
              className="md:hidden w-9 h-9 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors cursor-pointer flex items-center justify-center shrink-0"
              title="Open Navigation Menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            <button
              onClick={() => {
                const themes = ['light', 'dark', 'auto'];
                const nextIndex = (themes.indexOf(theme) + 1) % themes.length;
                setTheme(themes[nextIndex]);
              }}
              className="hidden md:block p-2.5 rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-650 dark:text-slate-350 hover:text-slate-900 dark:hover:text-white transition-colors cursor-pointer"
              title={`Current theme: ${theme}. Click to change.`}
            >
              {theme === 'light' && <Sun className="w-5 h-5" />}
              {theme === 'dark' && <Moon className="w-5 h-5" />}
              {theme === 'auto' && <Monitor className="w-5 h-5" />}
            </button>
            <Link
              to="/settings"
              className="hidden md:block p-2.5 rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-650 dark:text-slate-350 hover:text-slate-900 dark:hover:text-white transition-colors cursor-pointer"
              title="Settings"
            >
              <Settings className="w-5 h-5" />
            </Link>
          </div>
        </div>
      </nav>

      <main id="main-content">
        <AppRoutes
          fbUser={fbUser}
          isReady={isReady}
          customerProfile={customerProfile}
          setCustomerProfile={setCustomerProfile}
          loanAmount={loanAmount}
          setLoanAmount={setLoanAmount}
          loanTerm={loanTerm}
          setLoanTerm={setLoanTerm}
          activeBot={activeBot}
          setActiveBot={setActiveBot}
          calculateMonthlyPayment={calculateMonthlyPayment}
          interestRate={interestRate}
        />
      </main>

          {isReady && fbUser && !isChatOpen && isCxAgentEnabled && !isSearchPage && isChatSdkReady && (
            <div
              onClick={() => setIsChatOpen(true)}
              className="fixed bottom-6 right-6 z-[100] w-14 h-14 rounded-full flex items-center justify-center cursor-pointer shadow-2xl hover:scale-110 transition-all duration-300 animate-fade-in"
              style={{ backgroundImage: `linear-gradient(to top right, ${brandColorFrom}, ${brandColorTo})`, boxShadow: `0 25px 50px -12px ${brandColorFrom}50` }}
            >
              <MessageSquare className="w-6 h-6 text-slate-950" />
            </div>
          )}

          {/* Fixed Bottom Left Chat Messenger */}
          {isReady && fbUser && isChatOpen && isCxAgentEnabled && !isSearchPage && isChatSdkReady && (
            <div id="chat-messenger-wrapper" key="stable-chat-wrapper" className="fixed bottom-6 right-6 z-[100] w-[720px] h-[680px] rounded-3xl shadow-2xl overflow-hidden animate-fade-in">
              <chat-messenger
                ref={messengerRefCallback}
                url-allowlist="*"
                color-scheme={resolvedTheme}
                style={resolvedTheme === 'dark' ? {
                  width: '100%',
                  height: '100%',
                  '--chat-messenger-color--surface': '#020617',
                  '--chat-messenger-color--surface-container': '#0f172a',
                  '--chat-messenger-color--primary': '#10b981',
                  '--chat-messenger-color--primary-container': '#065f46',
                  '--chat-messenger-color--on-surface': '#f8fafc',
                  '--chat-messenger-color--on-surface-variant': '#94a3b8',
                  '--chat-messenger-color--on-primary': '#020617',
                  '--chat-messenger-color--outline': '#1e293b',
                  '--chat-messenger-font-family': '"Outfit", sans-serif',
                  '--chat-messenger-color--outline-variant': '#334155',
                  '--chat-messenger-color--outline-active': '#10b981',
                  '--chat-messenger-color--secondary': '#1e293b',
                  '--chat-messenger-internal-link-background': 'transparent',
                } : {
                  width: '100%',
                  height: '100%',
                    '--chat-messenger-color--surface': '#f8fafc',
                    '--chat-messenger-color--surface-container': '#f1f5f9',
                    '--chat-messenger-color--primary': '#10b981',
                    '--chat-messenger-color--primary-container': '#d1fae5',
                    '--chat-messenger-color--on-surface': '#0f172a',
                    '--chat-messenger-color--on-surface-variant': '#475569',
                    '--chat-messenger-color--on-primary': '#ffffff',
                    '--chat-messenger-color--outline': '#e2e8f0',
                    '--chat-messenger-font-family': '"Outfit", sans-serif',
                    '--chat-messenger-color--outline-variant': '#cbd5e1',
                    '--chat-messenger-color--outline-active': '#10b981',
                }}
              >
                <chat-messenger-container
                  chat-title={`${bankName} Assistant`}
                  chat-title-icon={resolvedIconUrl}
                  enable-file-upload
                  enable-audio-input
                >
                  <chat-reset-session-button
                    slot="titlebar-actions"
                    title-text="Start new chat"
                  ></chat-reset-session-button>
                  <chat-toggle-dialog-button
                    slot="titlebar-actions"
                    title-text-expanded="Collapse"
                    title-text-collapsed="Expand"
                  ></chat-toggle-dialog-button>
              <button
                slot="titlebar-actions"
                onClick={() => setIsGcpInfoModalOpen(true)}
                className="p-1 rounded-lg hover:bg-slate-500/10 dark:hover:bg-white/10 transition-all cursor-pointer flex items-center justify-center mr-1"
                title="GCP App Integration Info"
              >
                <GoogleCloudIcon className="w-4 h-4" />
              </button>
                  <chat-messenger-close-button
                    slot="titlebar-actions"
                    title-text="Close"
                    onClick={() => setIsChatOpen(false)}
                  ></chat-messenger-close-button>
                </chat-messenger-container>
              </chat-messenger>
            </div>
          )}

      {/* Mobile Slide-out Tray Menu */}
      {isMobileMenuOpen && (
        <div className="fixed inset-0 z-[200] md:hidden bg-black/50 backdrop-blur-sm animate-fade-in flex">
          {/* Sliding menu pane */}
          <div className="w-4/5 max-w-sm bg-white dark:bg-slate-900 h-full shadow-2xl border-r border-slate-200 dark:border-slate-800 flex flex-col justify-between overflow-y-auto">
            <div className="p-6 space-y-6">
              <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-4">
                <div className="flex items-center space-x-3">
                  <div 
                    className="w-8 h-8 rounded-lg flex items-center justify-center shadow-md text-slate-950"
                    style={{ backgroundImage: `linear-gradient(to top right, ${brandColorFrom}, ${brandColorTo})` }}
                  >
                    <Shield className="w-4 h-4 text-slate-950" />
                  </div>
                  <span className="text-base font-bold text-slate-900 dark:text-white tracking-tight">{bankName}</span>
                </div>
                <button 
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="p-2 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Mobile Search Input */}
              <div className="relative w-full px-1">
                <Search className="absolute left-4 top-3 w-4 h-4 text-slate-400" />
                <input 
                  type="text" 
                  placeholder="Search site..." 
                  className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-emerald-500/30 transition-all cursor-pointer shadow-sm hover:border-slate-300 dark:hover:border-slate-700"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && e.target.value.trim()) {
                      const query = e.target.value.trim();
                      e.target.value = ""; 
                      setIsMobileMenuOpen(false);
                      navigate('/search', { state: { initialQuery: query } });
                    }
                  }}
                />
              </div>

              {/* Navigation Items */}
              <div className="space-y-1 text-sm font-bold">
                <Link 
                  to="/"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/' ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Home</span>
                  {location.pathname === '/' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                </Link>

                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-4 pt-4 pb-1">Deposit Accounts</div>
                <Link 
                  to="/checking-accounts"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/checking-accounts' ? 'bg-slate-100 dark:bg-slate-800 text-teal-600 dark:text-teal-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Checking</span>
                  {location.pathname === '/checking-accounts' && <div className="w-1.5 h-1.5 rounded-full bg-teal-500"></div>}
                </Link>
                <Link 
                  to="/savings-accounts"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/savings-accounts' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Savings</span>
                  {location.pathname === '/savings-accounts' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                </Link>
                <Link 
                  to="/certificate-accounts"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/certificate-accounts' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Certificate Accounts</span>
                  {location.pathname === '/certificate-accounts' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                </Link>

                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-4 pt-4 pb-1">Credit & Cards</div>
                <Link 
                  to="/credit-cards"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/credit-cards' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Credit Cards</span>
                  {location.pathname === '/credit-cards' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                </Link>


                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-4 pt-4 pb-1">Home Financing</div>
                <Link 
                  to="/mortgages"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/mortgages' ? 'bg-slate-100 dark:bg-slate-800 text-cyan-600 dark:text-cyan-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Mortgages</span>
                  {location.pathname === '/mortgages' && <div className="w-1.5 h-1.5 rounded-full bg-cyan-500"></div>}
                </Link>
                <Link 
                  to="/mortgage-rates"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/mortgage-rates' ? 'bg-slate-100 dark:bg-slate-800 text-cyan-600 dark:text-cyan-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Mortgage Rates</span>
                  {location.pathname === '/mortgage-rates' && <div className="w-1.5 h-1.5 rounded-full bg-cyan-500"></div>}
                </Link>

                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-4 pt-4 pb-1">Product Tools</div>
                <Link 
                  to="/compare-products"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/compare-products' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Compare Products</span>
                  {location.pathname === '/compare-products' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                </Link>

                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-4 pt-4 pb-1">Support & Documentation</div>
                <Link 
                  to="/help-center"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/help-center' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Help Center</span>
                </Link>
                {fbUser && (
                  <Link 
                    to="/support/voice"
                    onClick={() => setIsMobileMenuOpen(false)}
                    className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/support/voice' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400' : 'text-slate-600 dark:text-slate-400'}`}
                  >
                    <span>Credit Card Support</span>
                    {location.pathname === '/support/voice' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                  </Link>
                )}
                {fbUser && (
                  <Link
                    to="/secure-messaging"
                    onClick={() => setIsMobileMenuOpen(false)}
                    className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/secure-messaging' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400 font-bold' : 'text-slate-600 dark:text-slate-400'}`}
                  >
                    <span>Secure Messages</span>
                    {location.pathname === '/secure-messaging' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                  </Link>
                )}
                <Link 
                  to="/fee-schedule"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/fee-schedule' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Fee Schedule</span>
                </Link>
                <Link 
                  to="/disclosures"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/disclosures' ? 'bg-slate-100 dark:bg-slate-800 text-sky-600 dark:text-sky-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Disclosures</span>
                </Link>
                <Link 
                  to="/locator"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/locator' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span>Find Branch/ATM</span>
                  {location.pathname === '/locator' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                </Link>
                {fbUser && (
                  <>
                    <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-4 pt-4 pb-1">Admin</div>
                    <Link
                      to="/admin"
                      onClick={() => setIsMobileMenuOpen(false)}
                      className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/admin' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400 font-bold' : 'text-slate-600 dark:text-slate-400'}`}
                    >
                      <span>Admin Portal</span>
                      {location.pathname === '/admin' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                    </Link>
                  </>
                )}
                {fbUser && (
                  <Link
                    to="/search"
                    onClick={() => setIsMobileMenuOpen(false)}
                    className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/search' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400 font-bold' : 'text-slate-600 dark:text-slate-400'}`}
                  >
                    <span>Search Site</span>
                    {location.pathname === '/search' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                  </Link>
                )}

                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-4 pt-4 pb-1">Preferences</div>
                <button 
                  onClick={() => {
                    const themes = ['light', 'dark', 'auto'];
                    const nextIndex = (themes.indexOf(theme) + 1) % themes.length;
                    setTheme(themes[nextIndex]);
                  }}
                  className="w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between text-slate-600 dark:text-slate-400"
                >
                  <span className="flex items-center gap-2.5">
                    {theme === 'light' && <Sun className="w-4 h-4" />}
                    {theme === 'dark' && <Moon className="w-4 h-4" />}
                    {theme === 'auto' && <Monitor className="w-4 h-4" />}
                    <span>Theme ({theme.charAt(0).toUpperCase() + theme.slice(1)})</span>
                  </span>
                </button>
                <Link 
                  to="/settings"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between ${location.pathname === '/settings' ? 'bg-slate-100 dark:bg-slate-800 text-emerald-600 dark:text-emerald-400' : 'text-slate-600 dark:text-slate-400'}`}
                >
                  <span className="flex items-center gap-2.5">
                    <Settings className="w-4 h-4" />
                    <span>Settings</span>
                  </span>
                  {location.pathname === '/settings' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>}
                </Link>
              </div>
            </div>

            <div className="p-6 border-t border-slate-100 dark:border-slate-800 text-[11px] text-slate-400">
              Secured digital context line. Tap outside to close tray.
            </div>
          </div>
          {/* Dismiss area */}
          <div className="flex-grow" onClick={() => setIsMobileMenuOpen(false)}></div>
        </div>
      )}

      {/* Footer */}

      <footer className="bg-white dark:bg-slate-950 border-t border-slate-200 dark:border-slate-900 py-16 px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-12">
          <div className="space-y-4">
            <div className="flex items-center space-x-3">
              <div 
                className={customLogoUrl ? "w-8 h-8 flex items-center justify-center" : "w-8 h-8 rounded-lg flex items-center justify-center"}
                style={customLogoUrl ? {} : { backgroundImage: `linear-gradient(to top right, ${brandColorFrom}, ${brandColorTo})` }}
              >
                      {customLogoUrl ? (
                        <img src={customLogoUrl} alt="Logo" className={`w-full h-full object-${logoFit}`} />
                      ) : (() => {
                        const Logo = IconMap[logoIcon] || Shield;
                        return <Logo className="w-5 h-5 text-slate-950" />;
                      })()}
              </div>
              <span className="text-lg font-bold tracking-tight text-slate-900 dark:text-white">{bankName}</span>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              {footerText}
            </p>
            {(window.env?.BUILD_VERSION || window.env?.BUILD_COMMIT_ID) && (
              <div className="text-[10px] text-slate-400 dark:text-slate-500 font-mono flex items-center gap-1.5 mt-1">
                <span>
                  Version: {window.env?.BUILD_VERSION || 'unknown'} (
                  {window.env?.BUILD_COMMIT_ID ? (
                    <a 
                      href={`https://github.com/GoogleCloudPlatform/fsi-gecx-bundle/commit/${window.env.BUILD_COMMIT_ID}`} 
                      target="_blank" 
                      rel="noopener noreferrer" 
                      className="hover:underline text-slate-500 dark:text-slate-400"
                    >
                      {window.env.BUILD_COMMIT_ID}
                    </a>
                  ) : (
                    'unknown'
                  )}
                  )
                </span>
                <button
                  onClick={() => setIsGcpEnvModalOpen(true)}
                  className="p-0.5 rounded hover:bg-slate-105 dark:hover:bg-slate-800/80 transition-colors cursor-pointer text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 flex items-center justify-center"
                  title="View GCP Environment Configuration"
                >
                  <GoogleCloudIcon className="w-3 h-3" />
                </button>
              </div>
            )}
          </div>

          <div>
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">Products</h4>
            <ul className="space-y-2 text-sm text-slate-500">
              <li><Link to="/checking-accounts" className={getFooterLinkClass('/checking-accounts')}>Checking Accounts</Link></li>
              <li><Link to="/savings-accounts" className={getFooterLinkClass('/savings-accounts')}>Savings Accounts</Link></li>
              <li><Link to="/certificate-accounts" className={getFooterLinkClass('/certificate-accounts')}>Certificate Accounts</Link></li>
              <li><Link to="/credit-cards" className={getFooterLinkClass('/credit-cards')}>Credit Cards</Link></li>
              <li><Link to="/mortgages" className={getFooterLinkClass('/mortgages')}>Mortgages</Link></li>
              <li><Link to="/mortgage-rates" className={getFooterLinkClass('/mortgage-rates')}>Mortgage Rates</Link></li>
              <li><Link to="/compare-products" className={getFooterLinkClass('/compare-products')}>Compare Products</Link></li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">Support</h4>
            <ul className="space-y-2 text-sm text-slate-500">
              <li><Link to="/help-center" className={getFooterLinkClass('/help-center')}>Help Center</Link></li>
              <li><Link to="/fee-schedule" className={getFooterLinkClass('/fee-schedule')}>Fee Schedule</Link></li>
              <li><Link to="/locator" className={getFooterLinkClass('/locator')}>Find Branch/ATM</Link></li>
              {fbUser && (
                <li><Link to="/support/voice" className={getFooterLinkClass('/support/voice')}>Credit Card Support</Link></li>
              )}
              {fbUser && (
                <li><Link to="/secure-messaging" className={getFooterLinkClass('/secure-messaging')}>Secure Messages</Link></li>
              )}
              <li><a href="/#security" className="hover:text-slate-900 dark:hover:text-white transition-colors">Security</a></li>
              <li><a href="/#calculator" className="hover:text-slate-900 dark:hover:text-white transition-colors">Rates</a></li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">Regulatory</h4>
            <ul className="space-y-2 text-sm text-slate-500">
              <li><Link to="/disclosures" className={getFooterLinkClass('/disclosures')}>Disclosures</Link></li>
              <li><a href="#" className="hover:text-slate-900 dark:hover:text-white transition-colors">Privacy Policy</a></li>
              <li><a href="#" className="hover:text-slate-900 dark:hover:text-white transition-colors">Terms of Service</a></li>
              <li><span className="font-medium" style={{ color: brandColorFrom }}>NCUA Insured</span></li>
            </ul>
          </div>
          </div>
        </footer>

        {isExportModalOpen && (
          <div className="fixed inset-0 z-[200] bg-black/50 backdrop-blur-sm flex items-center justify-center">
            <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 max-w-md w-full">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-4">Export Settings</h2>
              <p className="text-slate-600 dark:text-slate-400 mb-6">Choose the format for the exported file.</p>
              <div className="flex justify-end space-x-4">
                <button
                  onClick={() => setIsExportModalOpen(false)}
                  className="px-4 py-2 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-300 dark:hover:bg-slate-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleExport('json')}
                  className="px-4 py-2 rounded-full bg-emerald-500 hover:bg-emerald-600 text-white font-semibold transition-colors"
                >
                  JSON
                </button>
                <button
                  onClick={() => handleExport('yaml')}
                  className="px-4 py-2 rounded-full bg-teal-500 hover:bg-teal-600 text-white font-semibold transition-colors"
                >
                  YAML
                </button>
              </div>
            </div>
          </div>
        )}

      <GcpInfoModal
        isOpen={isGcpInfoModalOpen}
        onClose={() => setIsGcpInfoModalOpen(false)}
        title="CX Agent Studio"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            This conversational assistant is managed by <strong>CX Agent Studio</strong> (GECX), a Google Cloud Platform developer console used to define, monitor, and deploy backend tools, extension actions, and LLM guardrails.
          </p>
          <p>
            You can access the CX Agent Studio dashboard to view configuration states, runtime execution parameters, and guardrail settings using the link below:
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">CX Agent Studio Console</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Orchestrate agent definitions, tool configurations, and prompt rules.</p>
              </div>
              <div className="flex flex-col items-end gap-1.5 shrink-0">
                <a
                  href={`https://ces.cloud.google.com/projects/${projectId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs hover:underline"
                >
                  <span>View Console</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
                {appId && (
                  <a
                    href={`https://ces.cloud.google.com/projects/${cxProjectId || projectId}/locations/us/apps/${appId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs hover:underline"
                  >
                    <span>View Agent</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </div>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Documentation</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Learn about conversational agents, platform settings, and extensions.</p>
              </div>
              <a
                href="https://docs.cloud.google.com/customer-engagement-ai/conversational-agents/ps"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Docs</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Architecture Guide</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Read about the Home Loan Assistant topology, client upload triggers, and Document AI parsing.</p>
              </div>
              <a
                href="https://github.com/GoogleCloudPlatform/fsi-gecx-bundle/blob/main/docs/architecture/domain-workflows/origination/home_loan_preapproval_integration.md"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Design</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      </GcpInfoModal>

      <GcpInfoModal
        isOpen={isAuthInfoModalOpen}
        onClose={() => setIsAuthInfoModalOpen(false)}
        title="Identity & Authentication Integration"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
          <p>
            This user identity and authentication system uses <strong>Firebase Authentication</strong> integrated with <strong>GCP Identity Platform</strong>.
          </p>
          <p>
            Firebase Auth handles the client-side user sessions and JWT tokens, while GCP Identity Platform provides enterprise-grade identity configuration and multi-tenant providers.
          </p>
          <p>
            You can inspect the registered users, authentication providers, and token claims directly in the consoles using the links below:
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Firebase Auth Users</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">View user IDs, email verification status, and creation metadata.</p>
              </div>
              <a
                href={`https://console.firebase.google.com/project/${projectId}/authentication/users`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Users</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">GCP Identity Platform Providers</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Manage OAuth providers, sign-in methods, and security tokens.</p>
              </div>
              <a
                href={`https://console.cloud.google.com/customer-identity/providers?project=${projectId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Providers</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Firebase Auth Docs</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Learn about Firebase Authentication, integration APIs, and security rules.</p>
              </div>
              <a
                href="https://firebase.google.com/docs/auth"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Docs</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
            <hr className="border-slate-100 dark:border-slate-800" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-xs uppercase tracking-wider">Identity Platform Docs</h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Explore enterprise identity configuration, multi-tenancy, and advanced security settings.</p>
              </div>
              <a
                href="https://docs.cloud.google.com/identity-platform/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-emerald-500 hover:text-emerald-600 font-semibold text-xs shrink-0 hover:underline"
              >
                <span>View Docs</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </div>
      </GcpInfoModal>

       <GcpInfoModal
        isOpen={isGcpEnvModalOpen}
        onClose={() => setIsGcpEnvModalOpen(false)}
        title="GCP Environment Configuration"
        maxWidthClass="max-w-3xl"
      >
        <div className="space-y-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed text-left">
          <p>
            This application is deployed on <strong>Google Cloud Platform</strong>. Below are the key environment configurations and service integrations currently in use.
          </p>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-3 font-sans">
            <div className="space-y-2.5">
              <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                <span className="font-semibold text-slate-500 dark:text-slate-400">Build Version</span>
                <span className="font-mono text-slate-800 dark:text-slate-200">{window.env?.BUILD_VERSION || 'unknown'}</span>
              </div>
              <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                <span className="font-semibold text-slate-500 dark:text-slate-400">Build Commit ID</span>
                <span className="font-mono text-slate-800 dark:text-slate-200">{window.env?.BUILD_COMMIT_ID || 'unknown'}</span>
              </div>
              {window.env?.BUILD_PROJECT_ID && (
                <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                  <span className="font-semibold text-slate-500 dark:text-slate-400">Build Project ID</span>
                  <span className="font-mono text-slate-800 dark:text-slate-200">{window.env.BUILD_PROJECT_ID}</span>
                </div>
              )}
              {window.env?.BUILD_BUILD_ID && (
                <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                  <span className="font-semibold text-slate-500 dark:text-slate-400">Build ID</span>
                  <span className="font-mono text-slate-800 dark:text-slate-200">{window.env.BUILD_BUILD_ID}</span>
                </div>
              )}
              {window.env?.BUILD_LOCATION && (
                <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                  <span className="font-semibold text-slate-500 dark:text-slate-400">Build Location</span>
                  <span className="font-mono text-slate-800 dark:text-slate-200">{window.env.BUILD_LOCATION}</span>
                </div>
              )}
              {window.env?.BUILD_BUILD_ID && window.env.BUILD_BUILD_ID !== 'local-build' && (
                <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                  <span className="font-semibold text-slate-500 dark:text-slate-400">Cloud Build Link</span>
                  <a
                    href={`https://console.cloud.google.com/cloud-build/builds;region=${window.env.BUILD_LOCATION || 'us-central1'}/${window.env.BUILD_BUILD_ID}?project=${window.env.BUILD_PROJECT_ID || projectId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-emerald-500 hover:text-emerald-600 hover:underline flex items-center gap-0.5"
                  >
                    <span>View Build</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              )}
              <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                <span className="font-semibold text-slate-500 dark:text-slate-400">GCP Project ID</span>
                <span className="font-mono text-slate-800 dark:text-slate-200">{projectId || 'unknown'}</span>
              </div>


              <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                <span className="font-semibold text-slate-500 dark:text-slate-400">Banking API URL</span>
                <span className="font-mono text-slate-800 dark:text-slate-200">{window.env?.BANKING_API_URL || 'unknown'}</span>
              </div>
              <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                <span className="font-semibold text-slate-500 dark:text-slate-400">CCAI Platform Enabled</span>
                <span className="font-mono text-slate-800 dark:text-slate-200">{window.env?.ENABLE_CCAI ? 'Yes' : 'No'}</span>
              </div>
              {window.env?.ENABLE_CCAI && (
                <>
                  <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                    <span className="font-semibold text-slate-500 dark:text-slate-400">CCAI Host</span>
                    <span className="font-mono text-slate-800 dark:text-slate-200">{window.env?.CCAI_HOST || 'unknown'}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                    <span className="font-semibold text-slate-500 dark:text-slate-400">CCAI Company ID</span>
                    <span className="font-mono text-slate-800 dark:text-slate-200">{window.env?.CCAI_COMPANY_ID || 'unknown'}</span>
                  </div>
                </>
              )}
              {window.env?.STABLE_ENV_URL && (
                <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                  <span className="font-semibold text-slate-500 dark:text-slate-400">Stable Env URL</span>
                  <a
                    href={window.env.STABLE_ENV_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-emerald-500 hover:text-emerald-600 hover:underline flex items-center gap-0.5 break-all text-right max-w-[65%]"
                  >
                    <span>{window.env.STABLE_ENV_URL}</span>
                    <ExternalLink className="w-3 h-3 shrink-0" />
                  </a>
                </div>
              )}
              {window.env?.FEEDBACK_URL && (
                <div className="flex justify-between items-center text-xs pb-2 border-b border-slate-100 dark:border-slate-800">
                  <span className="font-semibold text-slate-500 dark:text-slate-400">Feedback URL</span>
                  <a
                    href={window.env.FEEDBACK_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-emerald-500 hover:text-emerald-600 hover:underline flex items-center gap-0.5"
                  >
                    <span>Link</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              )}
              {window.env?.CX_AGENT_STUDIO_VOICE_AGENT_DEPLOYMENT_NAME && (
                <div className="flex flex-col text-xs space-y-1 pb-2 border-b border-slate-100 dark:border-slate-800">
                  <div className="flex justify-between items-center w-full">
                    <span className="font-semibold text-slate-500 dark:text-slate-400 text-left">Credit Card Support Voice Agent Deployment</span>
                    {getCesAppUrl(window.env.CX_AGENT_STUDIO_VOICE_AGENT_DEPLOYMENT_NAME) && (
                      <a
                        href={getCesAppUrl(window.env.CX_AGENT_STUDIO_VOICE_AGENT_DEPLOYMENT_NAME)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-emerald-500 hover:text-emerald-600 hover:underline flex items-center gap-0.5 text-[10px] font-semibold"
                        title="View Agent in CES Console"
                      >
                        <span>View Agent</span>
                        <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    )}
                  </div>
                  <span className="font-mono text-[10px] text-slate-800 dark:text-slate-200 break-all text-left">{window.env.CX_AGENT_STUDIO_VOICE_AGENT_DEPLOYMENT_NAME}</span>
                </div>
              )}
              <div className="flex flex-col text-xs space-y-1 pb-2 border-b border-slate-100 dark:border-slate-800">
                <div className="flex justify-between items-center w-full">
                  <span className="font-semibold text-slate-500 dark:text-slate-400 text-left">Nova Horizon Bot Agent v2 Deployment</span>
                  {getCesAppUrl(window.env?.CX_AGENT_STUDIO_DEPLOYMENT_NAME) && (
                    <a
                      href={getCesAppUrl(window.env.CX_AGENT_STUDIO_DEPLOYMENT_NAME)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-emerald-500 hover:text-emerald-600 hover:underline flex items-center gap-0.5 text-[10px] font-semibold"
                      title="View Agent in CES Console"
                    >
                      <span>View Agent</span>
                      <ExternalLink className="w-2.5 h-2.5" />
                    </a>
                  )}
                </div>
                <span className="font-mono text-[10px] text-slate-800 dark:text-slate-200 break-all text-left">{window.env?.CX_AGENT_STUDIO_DEPLOYMENT_NAME || 'unknown'}</span>
              </div>
              {window.env?.CX_AGENT_STUDIO_UPLOAD_TOOL_NAME && (
                <div className="flex flex-col text-xs space-y-1 pb-2 border-b border-slate-100 dark:border-slate-800">
                  <div className="flex justify-between items-center w-full">
                    <span className="font-semibold text-slate-500 dark:text-slate-400 text-left">Nova Horizon Bot - Upload Tool Name</span>
                    {getCesAppUrl(window.env.CX_AGENT_STUDIO_UPLOAD_TOOL_NAME) && (
                      <a
                        href={getCesAppUrl(window.env.CX_AGENT_STUDIO_UPLOAD_TOOL_NAME)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-emerald-500 hover:text-emerald-600 hover:underline flex items-center gap-0.5 text-[10px] font-semibold"
                        title="View Agent in CES Console"
                      >
                        <span>View Agent</span>
                        <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    )}
                  </div>
                  <span className="font-mono text-[10px] text-slate-800 dark:text-slate-200 break-all text-left">{window.env.CX_AGENT_STUDIO_UPLOAD_TOOL_NAME}</span>
                </div>
              )}
              {window.env?.CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME && (
                <div className="flex flex-col text-xs space-y-1 pb-2 border-b border-slate-100 dark:border-slate-800">
                  <div className="flex justify-between items-center w-full">
                    <span className="font-semibold text-slate-500 dark:text-slate-400 text-left">Nova Horizon Bot - Populate Form Content Tool</span>
                    {getCesAppUrl(window.env.CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME) && (
                      <a
                        href={getCesAppUrl(window.env.CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-emerald-500 hover:text-emerald-600 hover:underline flex items-center gap-0.5 text-[10px] font-semibold"
                        title="View Agent in CES Console"
                      >
                        <span>View Agent</span>
                        <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    )}
                  </div>
                  <span className="font-mono text-[10px] text-slate-800 dark:text-slate-200 break-all text-left">{window.env.CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME}</span>
                </div>
              )}
              {window.env?.CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME && (
                <div className="flex flex-col text-xs space-y-1 pb-2">
                  <div className="flex justify-between items-center w-full">
                    <span className="font-semibold text-slate-500 dark:text-slate-400 text-left">Nova Horizon Bot - Get User Location Tool</span>
                    {getCesAppUrl(window.env.CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME) && (
                      <a
                        href={getCesAppUrl(window.env.CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-emerald-500 hover:text-emerald-600 hover:underline flex items-center gap-0.5 text-[10px] font-semibold"
                        title="View Agent in CES Console"
                      >
                        <span>View Agent</span>
                        <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    )}
                  </div>
                  <span className="font-mono text-[10px] text-slate-800 dark:text-slate-200 break-all text-left">{window.env.CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </GcpInfoModal>

        {/* Push Notification Toast/Dialog on Bottom Left */}
        {activeNotification && (
          <div className="fixed bottom-6 left-6 z-[200] max-w-sm w-80 sm:w-96 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl p-4 animate-fade-in flex flex-col gap-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
                  <Bell className="w-4 h-4" />
                </div>
                <div className="text-left">
                  <h4 className="text-sm font-bold text-slate-900 dark:text-white leading-tight">
                    {activeNotification.title}
                  </h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {activeNotification.receivedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>
              <button 
                onClick={() => setActiveNotification(null)}
                className="p-1.5 rounded-lg bg-slate-50 dark:bg-slate-800 text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors cursor-pointer"
                title="Dismiss notification"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-300 text-left leading-relaxed pl-10">
              {activeNotification.body}
            </p>
            <div className="flex justify-end pt-1 pl-10 gap-2">
              <button 
                onClick={() => setActiveNotification(null)}
                className="px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-colors text-xs font-semibold cursor-pointer"
              >
                Dismiss
              </button>
              {activeNotification.data?.type === 'support_message' && 
               (!activeNotification.data?.user_id || activeNotification.data.user_id === (customerProfile?.user_id || fbUser?.uid)) && (
                <button 
                  onClick={() => {
                    setActiveNotification(null);
                    navigate('/secure-messaging', { state: { selectThreadId: activeNotification.data.thread_id } });
                  }}
                  className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white transition-colors text-xs font-semibold cursor-pointer"
                >
                  View
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    );
}


function App() {
  return (
    <SettingsProvider>
      <AppContent />
    </SettingsProvider>
  );
}

export default App;
