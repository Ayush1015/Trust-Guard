
export default function TabNavigation({ activeTab, setActiveTab }) {
  const tabs = [
    { id: 'news', label: '📰 Fake News Detector' },
    { id: 'review', label: '⭐ Fake Review Detector' },
    { id: 'phishing', label: '🔗 Phishing URL Checker' }
  ];

  return (
    <ul className="nav nav-pills justify-content-center gap-2 p-2 mb-4 glass-card" style={{ maxWidth: '650px', margin: '0 auto' }}>
      {tabs.map((tab) => (
        <li className="nav-item flex-grow-1" key={tab.id}>
          <button
            className={`nav-link w-100 py-3 text-center ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
            type="button"
          >
            {tab.label}
          </button>
        </li>
      ))}
    </ul>
  );
}
