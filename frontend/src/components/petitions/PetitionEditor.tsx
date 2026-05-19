"use client";
import { useEffect, useCallback } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import {
  Bold, Italic, List, ListOrdered,
  Heading1, Heading2, Heading3,
  Undo, Redo, AlignJustify,
} from "lucide-react";

// Highlight [COMPLETAR] and [NÃO VERIFICADO] patterns
const HighlightPlaceholders = Extension.create({
  name: "highlightPlaceholders",
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey("highlightPlaceholders"),
        props: {
          decorations(state) {
            const decorations: Decoration[] = [];
            const doc = state.doc;
            const patterns = [/\[COMPLETAR[^\]]*\]/g, /\[NÃO VERIFICADO[^\]]*\]/gi, /\[Não Verificado[^\]]*\]/gi];

            doc.descendants((node, pos) => {
              if (!node.isText || !node.text) return;
              for (const pattern of patterns) {
                pattern.lastIndex = 0;
                let match;
                while ((match = pattern.exec(node.text)) !== null) {
                  const from = pos + match.index;
                  const to = from + match[0].length;
                  decorations.push(
                    Decoration.inline(from, to, {
                      class: "afj-placeholder-highlight",
                    })
                  );
                }
              }
            });

            return DecorationSet.create(doc, decorations);
          },
        },
      }),
    ];
  },
});

interface PetitionEditorProps {
  initialContent?: string;
  onChange?: (html: string) => void;
  readOnly?: boolean;
  placeholder?: string;
}

function ToolbarButton({
  onClick,
  active,
  title,
  children,
}: {
  onClick: () => void;
  active?: boolean;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onMouseDown={(e) => {
        e.preventDefault();
        onClick();
      }}
      title={title}
      className={`p-1.5 rounded text-sm transition-colors ${
        active
          ? "bg-afj-gold/20 text-afj-black"
          : "text-afj-black/50 hover:bg-afj-cream hover:text-afj-black"
      }`}
    >
      {children}
    </button>
  );
}

export function PetitionEditor({
  initialContent = "",
  onChange,
  readOnly = false,
  placeholder = "Conteúdo da petição...",
}: PetitionEditorProps) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        bulletList: {},
        orderedList: {},
      }),
      HighlightPlaceholders,
    ],
    content: initialContent || `<p>${placeholder}</p>`,
    editable: !readOnly,
    onUpdate({ editor }) {
      onChange?.(editor.getHTML());
    },
  });

  useEffect(() => {
    if (editor && initialContent && editor.getHTML() !== initialContent) {
      editor.commands.setContent(initialContent, false);
    }
  }, [initialContent, editor]);

  const setHeading = useCallback(
    (level: 1 | 2 | 3) => {
      editor?.chain().focus().toggleHeading({ level }).run();
    },
    [editor]
  );

  if (!editor) return null;

  return (
    <div className="border border-afj-cream-dark rounded-lg overflow-hidden bg-white">
      {!readOnly && (
        <div className="flex items-center gap-0.5 px-2 py-1.5 border-b border-afj-cream-dark bg-afj-cream/50 flex-wrap">
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBold().run()}
            active={editor.isActive("bold")}
            title="Negrito (Ctrl+B)"
          >
            <Bold size={14} />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleItalic().run()}
            active={editor.isActive("italic")}
            title="Itálico (Ctrl+I)"
          >
            <Italic size={14} />
          </ToolbarButton>

          <div className="w-px h-4 bg-afj-cream-dark mx-1" />

          <ToolbarButton
            onClick={() => setHeading(1)}
            active={editor.isActive("heading", { level: 1 })}
            title="Título 1"
          >
            <Heading1 size={14} />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => setHeading(2)}
            active={editor.isActive("heading", { level: 2 })}
            title="Título 2"
          >
            <Heading2 size={14} />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => setHeading(3)}
            active={editor.isActive("heading", { level: 3 })}
            title="Título 3"
          >
            <Heading3 size={14} />
          </ToolbarButton>

          <div className="w-px h-4 bg-afj-cream-dark mx-1" />

          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            active={editor.isActive("bulletList")}
            title="Lista"
          >
            <List size={14} />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            active={editor.isActive("orderedList")}
            title="Lista numerada"
          >
            <ListOrdered size={14} />
          </ToolbarButton>

          <div className="w-px h-4 bg-afj-cream-dark mx-1" />

          <ToolbarButton
            onClick={() => editor.chain().focus().undo().run()}
            active={false}
            title="Desfazer (Ctrl+Z)"
          >
            <Undo size={14} />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().redo().run()}
            active={false}
            title="Refazer (Ctrl+Y)"
          >
            <Redo size={14} />
          </ToolbarButton>

          <div className="ml-auto text-xs text-afj-black/30 flex items-center gap-1 pr-1">
            <AlignJustify size={10} />
            Justificado
          </div>
        </div>
      )}

      <EditorContent
        editor={editor}
        className="petition-editor-content prose prose-sm max-w-none p-4 min-h-[400px] focus-within:outline-none text-afj-black"
      />

      <style>{`
        .afj-placeholder-highlight {
          background-color: #fee2e2;
          color: #b91c1c;
          border-radius: 2px;
          padding: 0 2px;
          font-weight: 500;
        }
        .petition-editor-content .ProseMirror {
          outline: none;
          font-family: 'Times New Roman', Times, serif;
          font-size: 12pt;
          line-height: 1.8;
          text-align: justify;
        }
        .petition-editor-content .ProseMirror h1 {
          font-size: 14pt;
          font-weight: bold;
          text-align: center;
          margin: 1em 0 0.5em;
          text-transform: uppercase;
        }
        .petition-editor-content .ProseMirror h2 {
          font-size: 12pt;
          font-weight: bold;
          margin: 1em 0 0.3em;
          text-transform: uppercase;
        }
        .petition-editor-content .ProseMirror h3 {
          font-size: 12pt;
          font-weight: bold;
          margin: 0.8em 0 0.3em;
        }
        .petition-editor-content .ProseMirror p {
          margin: 0 0 0.8em;
          text-indent: 2em;
        }
        .petition-editor-content .ProseMirror ul,
        .petition-editor-content .ProseMirror ol {
          padding-left: 2em;
          margin: 0.5em 0;
        }
      `}</style>
    </div>
  );
}
