/** A heading word that rolls through three words (the animation has three stops). It sits on a fill, so green is never text. */
export function RotatingWord({ words }: { words: readonly string[] }) {
  const loop = [...words, words[0]];
  return (
    <>
      <span className="visually-hidden">{words.join(", ")}</span>
      <span className="rotating-word" aria-hidden="true">
        <span className="rotating-word__track">
          {loop.map((word, position) => (
            <em key={position}>{word}</em>
          ))}
        </span>
      </span>
    </>
  );
}
