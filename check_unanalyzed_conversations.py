#!/usr/bin/env python3
"""
Check Unanalyzed Conversations
===============================
Identifies ChatGPT conversations that have not been read or analyzed yet
"""

import json
from pathlib import Path
from typing import List, Dict, Set

def load_analyzed_conversations() -> Set[str]:
    """Load list of conversations that have been analyzed"""
    analysis_file = Path("organized_project/data/elysia_conversation_analysis.json")
    
    if not analysis_file.exists():
        return set()
    
    try:
        with open(analysis_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract file paths/names from analyses
        analyzed = set()
        for analysis in data.get('analyses', []):
            file_path = analysis.get('file_path', '')
            # Extract just the filename or conversation identifier
            if file_path:
                analyzed.add(Path(file_path).name.lower())
        
        return analyzed
    except Exception as e:
        print(f"Error loading analysis file: {e}")
        return set()

def get_chatgpt_conversations_from_browser() -> List[Dict[str, str]]:
    """
    Extract conversation titles from the browser snapshot.
    This is a manual list based on what we saw in the browser.
    """
    conversations = [
        # From "Your chat" section
        {"title": "Cursor browser interface", "section": "Your chat"},
        {"title": "Birth pattern by month", "section": "Your chat"},
        {"title": "3D printing concrete strength", "section": "Your chat"},
        {"title": "Georgia roadblock requirement", "section": "Your chat"},
        {"title": "Sheet rock crew size", "section": "Your chat"},
        {"title": "Dial lock pattern question", "section": "Your chat"},
        {"title": "Warlord how-to guide", "section": "Your chat"},
        {"title": "Arrest and extradition process", "section": "Your chat"},
        {"title": "Using hangers on PT wood", "section": "Your chat"},
        {"title": "Crack in windshield legality", "section": "Your chat"},
        {"title": "Analyzing Troll allegory", "section": "Your chat"},
        {"title": "New chat", "section": "Your chat"},
        {"title": "Image of dispatcher", "section": "Your chat"},
        {"title": "CapCut fade transition fix", "section": "Your chat"},
        {"title": "Branch · Video clip creation option", "section": "Your chat"},
        {"title": "Video clip creation option", "section": "Your chat"},
        {"title": "Legal distinction of stopping standing parking", "section": "Your chat"},
        {"title": "Add sleigh and reindeer", "section": "Your chat"},
        {"title": "Video about market prediction", "section": "Your chat"},
        {"title": "Kicker board size guide", "section": "Your chat"},
        {"title": "Porch construction advice", "section": "Your chat"},
        {"title": "Funny adult fortune saying", "section": "Your chat"},
        {"title": "Albany GA event search", "section": "Your chat"},
        {"title": "Poe's theme of death and time", "section": "Your chat"},
        {"title": "House and garage square footage", "section": "Your chat"},
        {"title": "Quantum gravity and scale", "section": "Your chat"},
        {"title": "Black hole minimum mass", "section": "Your chat"},
        {"title": "Bedroom addition value increase", "section": "Your chat"},
        
        # From "Project" section (Guardian GPT)
        {"title": "MN Adversarial AI Self-Improvement Are there any other elysia programs that need integration?", "section": "Project", "date": "Jul 24"},
        {"title": "MN AI Consciousness Debate Could you generate a safe point in a very complete list of all the work that we've completed so that I can transfer this over to a new conversation pick up exactly where we left", "section": "Project"},
        {"title": "MN Feedback Loop Evaluation for now just give me all the programming i can share with the main dream core", "section": "Project", "date": "Jul 10"},
        {"title": "MN ElysiaLoop-Core Event Loop Design can you give me a complete set of programs to integrate into the architect core so it can consolidate the elysia program?", "section": "Project", "date": "Jul 10"},
        {"title": "MN TrustEval-Action Implementation what modules you need to check?", "section": "Project"},
        {"title": "MN elysia 4 Could you generate a safe point in a very complete list of all the work that we've completed so that I can transfer this over to a new conversation pick up exactly where we left off without", "section": "Project"},
        {"title": "MN elysia 4 sub a Could you generate a safe point in a very complete list of all the work that we've completed so that I can transfer this over to a new conversation pick up exactly where we left off", "section": "Project"},
        {"title": "MN Improve Code Review What next", "section": "Project", "date": "Jul 10"},
        {"title": "MN Elysia Part 3 Development Could you generate a safe point in a very complete list of all the work that we've completed so that I can transfer this over to a new conversation pick up exactly where w", "section": "Project"},
        {"title": "MN How to make Bloody Mary I want her to contribute as she sees fit. I want her to have adversarial learning with other AIs. Pointing out problems with her plan. She needs a voice of doubt, a devil", "section": "Project"},
    ]
    
    return conversations

def normalize_title(title: str) -> str:
    """Normalize title for comparison"""
    return title.lower().strip()

def main():
    print("=" * 70)
    print("UNANALYZED CONVERSATIONS REPORT")
    print("=" * 70)
    print()
    
    # Load analyzed conversations
    analyzed = load_analyzed_conversations()
    print(f"📊 Found {len(analyzed)} analyzed files in analysis database")
    print()
    
    # Get conversations from ChatGPT
    chatgpt_conversations = get_chatgpt_conversations_from_browser()
    print(f"💬 Found {len(chatgpt_conversations)} conversations visible in ChatGPT")
    print()
    
    # Check which haven't been analyzed
    unanalyzed = []
    analyzed_matches = []
    
    for conv in chatgpt_conversations:
        title = conv['title']
        normalized = normalize_title(title)
        
        # Check if this conversation has been analyzed
        # We need to check if any analyzed file matches this conversation
        found = False
        for analyzed_file in analyzed:
            if normalized in analyzed_file or analyzed_file in normalized:
                found = True
                break
        
        if not found:
            unanalyzed.append(conv)
        else:
            analyzed_matches.append(conv)
    
    # Print results
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print()
    print(f"✅ Analyzed: {len(analyzed_matches)} conversations")
    print(f"❌ Unanalyzed: {len(unanalyzed)} conversations")
    print()
    
    if unanalyzed:
        print("=" * 70)
        print("UNANALYZED CONVERSATIONS")
        print("=" * 70)
        print()
        
        # Group by section
        by_section = {}
        for conv in unanalyzed:
            section = conv.get('section', 'Unknown')
            if section not in by_section:
                by_section[section] = []
            by_section[section].append(conv)
        
        for section, convs in by_section.items():
            print(f"\n📁 {section} ({len(convs)} conversations):")
            print("-" * 70)
            for i, conv in enumerate(convs, 1):
                title = conv['title']
                date = conv.get('date', '')
                date_str = f" [{date}]" if date else ""
                print(f"  {i}. {title}{date_str}")
        
        print()
        print("=" * 70)
        print("RECOMMENDATIONS")
        print("=" * 70)
        print()
        print("To analyze these conversations:")
        print("1. Export them from ChatGPT (see CHATGPT_DOWNLOAD_GUIDE.md)")
        print("2. Save them to: organized_project/data/chatgpt_conversations/")
        print("3. Run: python organized_project/elysia_conversation_reader.py")
        print()
    else:
        print("✅ All visible conversations have been analyzed!")
        print()
    
    # Save report
    report_file = Path("unanalyzed_conversations_report.json")
    report_data = {
        "total_chatgpt_conversations": len(chatgpt_conversations),
        "analyzed_count": len(analyzed_matches),
        "unanalyzed_count": len(unanalyzed),
        "unanalyzed_conversations": unanalyzed,
        "analyzed_conversations": analyzed_matches
    }
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    print(f"📄 Full report saved to: {report_file}")
    print()

if __name__ == "__main__":
    main()
