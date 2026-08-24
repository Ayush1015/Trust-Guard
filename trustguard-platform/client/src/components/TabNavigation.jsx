
export default function TabNavigation({ activeTab, setActiveTab }) {
  const tabs = [
    { id: 'news', label: '📰 Fake News Detector' },
    { id: 'review', label: '⭐ Fake Review Detector' },
    { id: 'phishing', label: '🔗 Phishing URL Checker' }
  ];

  return (
    <div className="segmented-control mb-5">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={`segmented-control-btn ${activeTab === tab.id ? 'active' : ''}`}
          onClick={() => setActiveTab(tab.id)}
          type="button"
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
