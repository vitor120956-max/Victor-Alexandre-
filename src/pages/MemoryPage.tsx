import { useMemo, useState } from 'react';
import { Brain, Download, HardDrive, LockKeyhole, Plus, Search, ShieldCheck, Trash2 } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { classNames, normalizeText } from '../lib/utils';

export function MemoryPage() {
  const { notes, tasks, messages, addNote, deleteNote, exportBackup, pushToast } = useApp();
  const [content, setContent] = useState('');
  const [tag, setTag] = useState('Ideia');
  const [query, setQuery] = useState('');
  const [activeTag, setActiveTag] = useState('Todas');
  const tags = ['Todas', ...Array.from(new Set(notes.map((note) => note.tag)))];
  const filtered = useMemo(() => notes.filter((note) => {
    const tagMatches = activeTag === 'Todas' || note.tag === activeTag;
    return tagMatches && normalizeText(`${note.content} ${note.tag}`).includes(normalizeText(query));
  }), [activeTag, notes, query]);
  const bytes = new Blob([JSON.stringify({ notes, tasks, messages })]).size;
  const storage = bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!content.trim()) return;
    addNote(content, tag);
    pushToast('Nota guardada na memória', tag);
    setContent('');
  };

  return (
    <div className="memory-page">
      <header className="page-heading">
        <div><span className="eyebrow">CONTEXTO PERSISTENTE</span><h1>Memória<span>.</span></h1><p>Ideias e decisões importantes, disponíveis quando você precisar.</p></div>
        <button className="button button-secondary" onClick={exportBackup}><Download size={17} /> Exportar backup</button>
      </header>
      <div className="memory-layout">
        <div className="memory-main">
          <section className="panel note-composer-panel">
            <div className="note-composer-heading"><span><Plus size={18} /></span><div><h2>Guardar uma nova memória</h2><p>Escreva em linguagem natural. Você poderá buscar depois.</p></div></div>
            <form onSubmit={submit}>
              <textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="Ex.: O JARVIS deve pedir confirmação antes de qualquer ação externa..." rows={3} maxLength={1200} required />
              <div className="note-form-footer"><label>Categoria<input value={tag} onChange={(event) => setTag(event.target.value)} maxLength={30} placeholder="Ideia" /></label><span>{content.length}/1200</span><button className="button button-primary" disabled={!content.trim()}>Guardar memória</button></div>
            </form>
          </section>
          <div className="memory-toolbar">
            <div className="tag-filters">{tags.map((item) => <button key={item} className={classNames(activeTag === item && 'active')} onClick={() => setActiveTag(item)}>{item}</button>)}</div>
            <label className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar na memória..." aria-label="Buscar na memória" /></label>
          </div>
          <div className="notes-grid">
            {filtered.map((note) => (
              <article className="note-card" key={note.id}>
                <div className="note-card-top"><span>{note.tag}</span><button onClick={() => deleteNote(note.id)} aria-label="Excluir nota"><Trash2 size={15} /></button></div>
                <p>{note.content}</p>
                <time>{new Date(note.createdAt).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' }).replace('.', '')} · {new Date(note.createdAt).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</time>
              </article>
            ))}
            {filtered.length === 0 && <div className="empty-state memory-empty"><span><Brain size={25} /></span><h3>Nenhuma memória encontrada</h3><p>Tente outro termo ou guarde uma nova ideia acima.</p></div>}
          </div>
        </div>
        <aside className="memory-aside">
          <section className="panel memory-stat-card"><span className="memory-big-icon"><Brain size={25} /></span><strong>{notes.length}</strong><span>memórias guardadas</span><div><span>{tags.length - 1} categorias</span><span>{storage} locais</span></div></section>
          <section className="panel privacy-card"><span className="eyebrow">PRIVACIDADE</span><h2>Seu contexto continua seu.</h2><div><LockKeyhole size={17} /><p>As notas ficam no armazenamento deste navegador. Não há sincronização automática.</p></div><div><ShieldCheck size={17} /><p>O backup é gerado localmente. Guarde o arquivo em um local seguro.</p></div><div><HardDrive size={17} /><p>Limpar os dados do navegador pode apagar a memória. Exporte regularmente.</p></div></section>
        </aside>
      </div>
    </div>
  );
}
