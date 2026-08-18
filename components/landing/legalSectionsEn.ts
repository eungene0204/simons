// English versions of the Terms of Service and Privacy Policy sections.
// The Korean text in TermsOfServicePage.tsx / PrivacyPolicyPage.tsx is the legally
// authoritative version; this translation is provided for convenience and should be
// reviewed by counsel before being relied on.

export type LegalSection = {
  title: string;
  body?: string[];
  list?: string[];
  table?: Array<{ label: string; content: string }>;
};

export const createTermsSectionsEn = (companyName: string, serviceName: string): LegalSection[] => [
  {
    title: "Article 1 (Purpose)",
    body: [
      `These Terms of Service (the "Terms") set out the rights, obligations, responsibilities and other necessary matters between ${companyName} (the "Company") and users in connection with the use of ${serviceName} and related services (the "Service") provided by the Company.`,
    ],
  },
  {
    title: "Article 2 (Definitions)",
    body: ["The main terms used in these Terms have the following meanings."],
    list: [
      `"Service" means the ${serviceName} website and the investment research tools, strategy design, backtesting, strategy validation and optimization, historical data analysis, AI analysis features, and virtual-account and paper-trading features provided by the Company.`,
      '"User" means members and non-members who use the Service under these Terms.',
      '"Member" means a person who has created an account through the procedure set by the Company and may use the Service on an ongoing basis.',
      '"Strategy" means a combination of conditions, indicators, filters and risk settings that a User has entered or configured directly.',
      '"Backtest" means the simulation feature that calculates a Strategy entered by a User against historical data.',
      '"Virtual account" means the feature that manages simulated trading records without any real money, orders, executions, deposits or withdrawals.',
      '"AI analysis features" means features that use statistical models or artificial-intelligence technology to display backtest result summaries, strategy composition assistance and historical-data-based analytical information.',
      '"Plan" means a combination of Service usage limits and pricing conditions set by the Company, including free and paid plans.',
      '"Paid service" means features, products or subscriptions that the Company provides on the condition of separate payment.',
    ],
  },
  {
    title: "Article 3 (Effect and Amendment of the Terms)",
    list: [
      "These Terms take effect when posted on the Service screen or otherwise notified to Users by reasonable means.",
      "The Company may amend these Terms to the extent that it does not violate applicable laws such as the Act on the Regulation of Terms and Conditions.",
      "When the Company amends the Terms, it will announce the effective date, the changes and the reasons for them at least 7 days before the effective date. Changes that are unfavorable to Users or material will be announced at least 30 days in advance and, where possible, notified individually by e-mail or in-Service notification.",
      "A User who does not agree to the amended Terms may stop using the Service and terminate the service agreement. Continued use of the Service after the effective date of the amended Terms is deemed acceptance of the amended Terms.",
    ],
  },
  {
    title: "Article 4 (Formation of the Service Agreement)",
    list: [
      "The service agreement is formed when a User agrees to these Terms, applies for use through the procedure set by the Company, and the Company accepts the application.",
      "Persons under 14 years of age may not register as Members.",
      "The Company may refuse an application or terminate the service agreement if the User has entered false information or misappropriated another person's information, if there is a risk of interfering with the operation of the Service, or if the User has a record of violating applicable laws or these Terms.",
      "Members must reflect the latest information through the Service screen or the method set by the Company when information provided during registration or use changes.",
    ],
  },
  {
    title: "Article 5 (Account Management)",
    list: [
      "Members are responsible for managing their IDs, passwords, authentication methods and account access rights.",
      "Members may not transfer, lend, share or pledge their accounts to third parties.",
      "Members must notify the Company immediately upon becoming aware of account theft or unauthorized use by a third party and follow the Company's instructions, if any.",
      "The Company is not liable for damages arising from a Member's negligent account management or failure to notify the Company promptly, unless caused by the Company's willful misconduct or gross negligence.",
    ],
  },
  {
    title: "Article 6 (Provision of the Service)",
    body: ["The Company may provide Users with the following services."],
    list: [
      "Creating, saving, editing and viewing user-generated strategies",
      "Backtesting on historical data and calculating performance metrics",
      "Historical-data-based strategy validation tools such as parameter optimization and walk-forward analysis",
      "Display of charts, technical indicators, financial indicators, prices, news and historical statistics",
      "Backtest result summaries, strategy composition assistance and historical-data-based analytical information using AI analysis features",
      "Virtual accounts and paper trading in which no real money is used",
      "Explanatory, summary and comparison screens that support strategy research",
      "Other investment research and simulation tools determined by the Company",
    ],
  },
  {
    title: "Article 7 (Financial Disclaimer)",
    list: [
      `${serviceName} is an investment research and simulation tool provided as software-as-a-service (SaaS). The Company does not engage in investment advisory business, discretionary investment business, investment dealing, investment brokerage or any other financial investment business or quasi-investment-advisory business under the Financial Investment Services and Capital Markets Act.`,
      "The Company does not provide advice on investment decisions concerning, or the value of, any specific financial investment product. Fees for paid services are consideration for the use of software such as calculation tools, data display and simulation features, and not consideration for investment advice.",
      "Backtest results, indicators, charts, statistics and explanations displayed in the Service are information calculated on the basis of historical data or conditions entered by the User.",
      "Results of the Service do not constitute investment recommendations, stock recommendations, portfolio recommendations, market forecasts or suggestions of buy or sell timing.",
      "The Company does not provide personalized financial advice based on a User's age, asset size, income, investment objectives or risk profile.",
      "Historical-data-based results do not guarantee future returns or avoidance of losses. All investment decisions and the responsibility for them rest solely with the User.",
      "Backtest and simulation results may differ from actual results because of execution prices, transaction costs, slippage, liquidity, and limits on the scope and accuracy of data in real trading.",
      "Virtual accounts and paper trading do not provide real order, execution, settlement, deposit, payment or withdrawal functions.",
    ],
  },
  {
    title: "Article 8 (Notice Regarding AI Analysis Features)",
    list: [
      "Information generated or displayed by AI analysis features is reference information based on historical data and statistical models, and is not an investment recommendation, strategy recommendation, market forecast or personalized advice.",
      "Output of AI analysis features may contain errors, inaccuracies, omissions or statements that differ from fact.",
      "Users must not rely on the output of AI analysis features as-is as the basis for investment decisions, and must verify important information directly against primary sources such as official disclosures.",
      "The Company does not warrant the accuracy, completeness or fitness for a particular purpose of the output of AI analysis features.",
    ],
  },
  {
    title: "Article 9 (Data and External Information)",
    list: [
      "Market data, financial data, news, charts and indicators may be based on external providers or public data.",
      "Prices displayed in the Service may be delayed rather than real-time, or collected as of a specific point in time.",
      "External data may be delayed, missing, erroneous, corrected or discontinued.",
      "Users are responsible for the accuracy and legality of the strategies, conditions, notes and virtual-account records they enter.",
      "Users must verify primary sources such as official disclosures, exchanges, financial institutions and data providers before making any actual investment or trade.",
    ],
  },
  {
    title: "Article 10 (Changes to and Suspension of the Service)",
    list: [
      "The Company may change or discontinue all or part of the Service for operational or technical reasons.",
      "The Company may temporarily suspend the Service for unavoidable reasons such as scheduled maintenance, incident response, security measures, failures of external data providers or force majeure.",
      "The Company will give prior notice of material changes or extended suspension of the Service, but may give notice afterwards where the cause is difficult for the Company to foresee or control.",
    ],
  },
  {
    title: "Article 11 (Plans and Usage Limits)",
    list: [
      "The Company may set different usage limits per Plan, such as the number of virtual accounts that can be created, the number of strategies that can be saved, the monthly number of backtests, and the initial simulated capital of virtual accounts.",
      "Usage limits, prices and detailed conditions per Plan are displayed on the pricing screen, and any changes are announced in accordance with Article 3.",
      "The initial simulated capital of a virtual account is not real money and is never convertible into cash, points or monetary value under any circumstances.",
      "The Company may restrict abnormal or excessive use within a reasonable scope to ensure stable operation of the Service.",
    ],
  },
  {
    title: "Article 12 (Refund Policy)",
    list: [
      `Where ${companyName} provides ${serviceName} paid services, the service name, price, payment method, service period, terms of use, and withdrawal and refund conditions are displayed on the screen before payment.`,
      "If, after the first payment, the User has not used any paid feature — including strategy creation, AI analysis, backtesting, walk-forward validation, Monte Carlo simulation or other paid features — even once, a full refund is available after verification of the payment and usage records.",
      "If a paid feature has been used one or more times, refunds are limited due to the nature of digital content and online services provided immediately. Use of the Service includes strategy creation, AI analysis, running backtests, running walk-forward analysis, running Monte Carlo simulation, downloading data and use of other paid features.",
      "In case of duplicate payment, incorrect payment due to a system error, or abnormal payment caused by a problem in the Company's payment system, a full refund is made after verification of the payment record.",
      "If use of the Service is impossible for an extended period, or normal provision of the Service is difficult, for reasons attributable to the Company, the Company may either extend the service period or provide a full refund, taking into account the cause and duration of the failure and its impact on use of the Service.",
      "The method and scope of compensation for Service failures are reasonably determined by the Company in accordance with applicable laws, these Terms and the Company's operating policies.",
      "Paid Plans may be provided on a monthly recurring-payment basis, in which case they are automatically renewed and charged each billing cycle unless the User cancels. The Company discloses the terms of automatic renewal on the screen before payment.",
      "Users may cancel automatic payment at any time through in-Service features or customer support. After cancellation, the paid service remains available for the period already paid, and no further charges are made from the next billing date.",
      "Users who wish to receive a refund may apply through customer support. The Company reviews eligibility after checking payment information, whether paid features have been used, and Service usage records.",
      "Where a refund is approved, the Company processes it in principle within 3–7 business days. The actual completion time may vary depending on the processing schedule of the payment provider, such as the card company, payment gateway or simple-payment provider.",
      "Where a refund or withdrawal is required by applicable law, that law prevails.",
      "Changing or cancelling a Plan does not change the initial simulated capital or balances of virtual accounts already created, and features exceeding the Plan limits may be restricted.",
      "Free trials, coupons, promotions and partial-refund conditions follow the conditions separately announced.",
    ],
  },
  {
    title: "Article 13 (User Obligations and Prohibited Conduct)",
    body: ["Users must not engage in any of the following conduct."],
    list: [
      "Using another person's account or information without authorization",
      "Entering false information or providing incorrect information to the Company",
      "Using the Service or its output for unlawful acts such as actual investment solicitation, discretionary management on behalf of others, paid advisory services, illegal 'reading' schemes, market manipulation or use of undisclosed information",
      "Compromising the security, servers, network, database or API of the Service, or causing excessive load",
      "Collecting, copying, storing or reselling the Service or its data without authorization by automated means",
      "Copying, distributing, selling, lending, reverse-engineering, decompiling or disassembling the Service or software without authorization",
      "Infringing the intellectual property rights, personal information, trade secrets, reputation or credit of the Company or third parties",
      "Violating applicable laws, these Terms, Service operating policies or precautions announced by the Company",
    ],
  },
  {
    title: "Article 14 (Intellectual Property and User Content)",
    list: [
      "Rights to the Service, software, screens, database structure, documents, trademarks and logos belong to the Company or the rightful owner.",
      "Rights to user content such as strategies, conditions and notes entered directly by Users belong to the Users.",
      "Users permit the Company to use user content to the extent necessary for Service operation, storage, backup, synchronization, screen display, customer support and error analysis.",
      "Users may not commercially resell the Service or provide it to third parties without the Company's prior consent.",
    ],
  },
  {
    title: "Article 15 (Protection of Personal Information)",
    list: [
      "The Company protects Users' personal information in accordance with the Personal Information Protection Act and other applicable laws.",
      "The purposes of processing, items collected, retention and use periods, provision to third parties, outsourcing, overseas transfer, methods of exercising User rights and the personal information protection officer are set out in a separate Privacy Policy.",
      "The Company posts the Privacy Policy on the Service screen or a linked screen.",
    ],
  },
  {
    title: "Article 16 (Provision of Information and Notices)",
    list: [
      "The Company may provide information about Service operation, maintenance, changes, failures, security, payment, and changes to the Terms or policies by reasonable means such as the Service screen, e-mail or notifications.",
      "The Company does not provide commercial advertising information to which the User has not consented beyond the scope permitted by applicable law.",
      "Users must check and comply with guidance, restrictions and precautions announced by the Company in connection with use of the Service.",
    ],
  },
  {
    title: "Article 17 (Restriction of Use and Termination)",
    list: [
      "Members may request termination of the service agreement at any time through in-Service features or customer support.",
      "If a User violates these Terms or applicable laws, the Company may restrict use of the Service or terminate the service agreement after prior notice.",
      "In case of urgent security risk, unlawful conduct, infringement of others' rights or disruption of Service operation, the Company may take necessary measures without prior notice.",
      "Upon termination of the service agreement, the Company retains or deletes Member information in accordance with applicable laws and the Privacy Policy.",
    ],
  },
  {
    title: "Article 18 (Limitation of Liability)",
    list: [
      "The Company is not liable where it cannot provide the Service for reasons beyond its reasonable control, such as natural disasters, war, terrorism, power outages, network failures, cloud failures or failures of external data providers.",
      "The Company is not liable for Service failures or damages caused by reasons attributable to the User.",
      "The Company is not responsible for the accuracy, reliability or legality of information that Users enter, store or publish through the Service.",
      "The Company is not liable for the results of actual investment decisions and trades made by Users on the basis of information or simulation results displayed in the Service.",
      "The Company is not liable for damages in connection with use of free services unless caused by its willful misconduct or gross negligence.",
      "The Company's liability in connection with paid services may be limited, to the extent permitted by applicable law, to the fees paid for the paid service in which the damage occurred; this limitation does not apply to damages caused by the Company's willful misconduct or gross negligence.",
      "The limitations in this Article do not apply to the extent they conflict with mandatory provisions such as the Act on the Regulation of Terms and Conditions.",
    ],
  },
  {
    title: "Article 19 (Damages)",
    list: [
      "If the Company or a User causes damage to the other party by violating these Terms or applicable laws, the party at fault must compensate for the damage.",
      "If a User causes damage to the Company or a third party through prohibited conduct under Article 13, the User must compensate for the damage.",
    ],
  },
  {
    title: "Article 20 (Dispute Resolution and Governing Law)",
    list: [
      "The Company and Users will consult in good faith to resolve amicably any dispute arising in connection with use of the Service.",
      "E-commerce or consumer disputes may be handled in accordance with applicable laws and consumer dispute resolution standards, and Users may apply for mediation to dispute resolution bodies such as the Korea Consumer Agency.",
      "These Terms are interpreted in accordance with the laws of the Republic of Korea.",
      "Where litigation is brought between the Company and a User, the competent court is determined under applicable laws such as the Civil Procedure Act.",
    ],
  },
  {
    title: "Article 21 (Miscellaneous)",
    list: [
      "Matters not provided for in these Terms follow applicable laws, individual Service operating policies and general commercial practice.",
      "The Company may establish separate terms of use or operating policies for specific services where necessary; where such separate terms or policies conflict with these Terms, the separate terms or policies prevail.",
    ],
  },
];

export const privacySectionsEn: LegalSection[] = [
  {
    title: "Article 1 (Purpose)",
    body: [
      'nullspace (the "Company") complies with the Personal Information Protection Act and related laws to process personal information lawfully and manage it securely, in order to protect the freedom and rights of data subjects. In accordance with Article 30 of the Personal Information Protection Act, the Company establishes and discloses this Privacy Policy to inform data subjects of the procedures and standards for processing and protecting personal information and to handle related grievances promptly and smoothly.',
    ],
  },
  {
    title: "Article 2 (Personal Information Processed)",
    body: [
      "The Company provides sign-up and login only through Google social login via Supabase, and does not directly collect or store users' passwords.",
    ],
    table: [
      {
        label: "Sign-up and login",
        content:
          "E-mail address, name or nickname, profile image URL, Google OAuth provider identifier and e-mail verification status provided when logging in with Google via Supabase",
      },
      {
        label: "Service usage information",
        content:
          "Strategy names, strategy descriptions, condition expressions, investment universes, backtest requests and results, strategy save and validation history, watchlists, virtual-account names, virtual order/execution/holding records, and conversation messages and questions entered into AI analysis features",
      },
      {
        label: "Automatically generated information",
        content: "Last login time, and error logs and security event records generated during Service operation",
      },
      {
        label: "Plan and usage information",
        content:
          "Current plan, monthly backtest usage, and — where paid services are introduced — the minimum information needed for payment status and refund processing",
      },
    ],
  },
  {
    title: "Article 3 (Purposes of Processing)",
    list: [
      "Identifying members, maintaining login, protecting accounts and preventing misuse",
      "Providing Service features such as user-generated strategies, backtests, historical performance analysis, virtual accounts and watchlists",
      "Performing calculations and analyses requested by users, such as generating responses from AI analysis features",
      "Saving strategies, viewing execution history, synchronizing settings and recovering from errors",
      "Ensuring Service stability, analyzing failures, security checks and detecting abnormal use",
      "Responding to customer inquiries, notifying changes to terms or policies, and Service operation notices",
      "Managing per-plan usage limits and, where paid services are introduced, payment, settlement and refund processing",
    ],
  },
  {
    title: "Article 4 (Retention and Use Period)",
    list: [
      "Member information is retained until membership withdrawal or termination of the service agreement. Information that must be retained under applicable laws is stored separately for the required period.",
      "Strategies, backtests, validation results, watchlists, virtual accounts and paper-trading records are retained until deleted by the user or until the account is closed. Deletion may take a reasonable time to propagate to backup or disaster-recovery storage.",
      "Error logs and security event records generated during Service operation are retained for a limited period for stability and security purposes and then destroyed.",
      "Where paid services are introduced, records are retained under the Act on Consumer Protection in Electronic Commerce: 5 years for contracts or withdrawal, 5 years for payment and supply of goods, and 3 years for consumer complaints or dispute handling.",
    ],
  },
  {
    title: "Article 5 (Provision to Third Parties)",
    list: [
      "The Company does not provide users' personal information to third parties beyond the purposes set out in this Policy.",
      "Exceptions apply where the user has given prior consent or where required by law, in which case the recipient, items provided, purpose of use and retention period are disclosed.",
    ],
  },
  {
    title: "Article 6 (Outsourcing and Overseas Transfer)",
    body: [
      "The Company outsources tasks necessary for providing the Service to the following external services, and personal information may be processed (stored or processed under outsourcing) overseas in the course of doing so. Transfer occurs by transmission over the network when the Service is used, and the retention period lasts until membership withdrawal or termination of the outsourcing contract.",
    ],
    table: [
      {
        label: "Member authentication",
        content:
          "Supabase Inc. (United States, etc.) — e-mail address, name, profile information and OAuth identifier for Supabase OAuth authentication and the Company's JWT session handling",
      },
      {
        label: "Servers and data storage",
        content: "Cloud hosting providers — Service usage information in general, for Service operation and data storage",
      },
      {
        label: "AI computation",
        content:
          "AI computing infrastructure providers (United States, etc.) — conversation messages and strategy text entered by users, processed to generate AI analysis responses (used only for immediate response generation)",
      },
      {
        label: "Payment processing (when introduced)",
        content:
          "Payment gateway — designed so that core payment-method data such as full card numbers is processed by the payment gateway and not stored directly by the Company.",
      },
    ],
    list: [
      "The names of processors in the actual operating environment, destination countries, transferred items and contact details are confirmed and announced on the Service screen or in a separate notice.",
      "Users who do not wish their personal information to be transferred overseas may refrain from registering or request suspension of the transfer through customer support. However, since overseas transfer is essential to providing the Service, refusing the transfer may restrict use of the Service.",
    ],
  },
  {
    title: "Article 7 (Cookies and Session Information)",
    list: [
      "The Company may use cookies and browser storage to keep users logged in, verify security and store display settings. The session token (JWT) used to keep users logged in is stored in a cookie in the user's browser and is not separately stored on the Company's servers.",
      "Users may refuse or delete cookies through browser settings. However, restricting cookies or session storage may prevent some features such as login, strategy creation, saving and virtual accounts from working properly.",
    ],
  },
  {
    title: "Article 8 (User Rights and How to Exercise Them)",
    list: [
      "Users may request the Company to access, correct, delete or suspend processing of their personal information, or withdraw consent.",
      "Members may request account deletion and termination of Service use through customer support.",
      "The Company acts without delay in accordance with applicable laws after verifying the identity of the requester. Some requests may be restricted where retention is required by law or where protection of other users' rights is necessary.",
      "The Company does not allow registration by children under 14 and does not collect personal information of children under 14. If it is found that information of a child under 14 has been collected, it is destroyed without delay.",
    ],
  },
  {
    title: "Article 9 (Destruction of Personal Information)",
    list: [
      "The Company destroys personal information without delay when the retention period has expired or the purpose of processing has been achieved.",
      "Electronic files are deleted so that recovery or reproduction is difficult, and paper documents such as printouts are shredded or incinerated.",
      "Information that must be retained under applicable laws is disclosed with its legal basis and items in accordance with Article 4, and stored in a separate storage area or with restricted access rights.",
    ],
  },
  {
    title: "Article 10 (Security Measures)",
    list: [
      "The Company limits access to personal information to those who need it for their work and manages access records.",
      "The Company does not store users' passwords directly; authentication is handled by Supabase Google login and session tokens issued by the Company, and authentication tokens and key configuration values are managed securely.",
      "Personal information is protected through encryption in transit, security updates, monitoring for failures and breaches, and backup and recovery procedures.",
      "Because investment strategies, backtest results and virtual-account records contain users' research data, access controls are applied to prevent unauthorized access and external exposure.",
    ],
  },
  {
    title: "Article 11 (Automated Decision-Making and AI Features)",
    list: [
      "The Service's AI summary, explanation, strategy interpretation and backtest analysis assistance features are tools for explaining what users have entered and the results of historical-data-based calculations.",
      "Conversation content and strategy text entered into AI analysis features are processed to generate responses; the Company does not use them to train AI models without the user's separate consent.",
      "The Company does not provide investment recommendations, stock recommendations, portfolio recommendations, buy/sell timing suggestions or personalized financial advice through AI features.",
      "Users may request an explanation of AI or automated processing results and, if necessary, raise objections through customer support.",
    ],
  },
  {
    title: "Article 12 (Changes to this Policy)",
    list: [
      "The Company may revise this Policy when laws, the Service structure or the way personal information is processed change.",
      "For material changes, the effective date, the changes and the reasons are announced in advance on the Service screen.",
    ],
  },
];
