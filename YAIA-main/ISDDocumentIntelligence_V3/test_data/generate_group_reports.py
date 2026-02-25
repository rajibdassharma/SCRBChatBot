"""
Generate 25 intelligence Log Report PDFs for group activities.
Uses Bread Crumb theory: past → current → future trail with cross-references.
"""

import os
from fpdf import FPDF

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "groups")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# 25 Intelligence Log Reports
# ──────────────────────────────────────────────────────────────────────────────
REPORTS = [
    # ── Tech Innovation Lab (5 reports) ──────────────────────────────────────
    {
        "filename": "LOG-001_TechInnovationLab_CodingBootcamp.pdf",
        "tms_id": "TMS-2025-0412",
        "originator": "Open Source Cell",
        "date": "Mar 18 2025 10:15 AM",
        "theatre": "Social Media",
        "priority": "Informative",
        "subject": "Tech Innovation Lab - Coding Bootcamp Conducted",
        "input": (
            "It was observed that the Tech Innovation Lab, coordinated by Amit Sharma, "
            "conducted a three-day Coding Bootcamp at the Pinnacle Global Solutions campus "
            "in Manyata Tech Park, Bengaluru from March 15-17, 2025. Approximately 200 "
            "participants attended including employees and external college students. "
            "Vikram Patel and Srinivas Reddy served as lead instructors covering Python, "
            "machine learning, and cloud computing. Sneha Krishnamurthy and Arjun Nair "
            "organized logistics. Social media posts by Tanvi Bhatt and Manpreet Singh "
            "indicate the event was well received. Several posts mentioned that this was "
            "the first of many planned events. Harpreet Singh posted photos from the event "
            "showing collaboration between employees from Engineering and Data & Analytics "
            "departments. It was noted that participants from IIT Bangalore and IIIT Hyderabad "
            "were also present, suggesting the Lab is building external academic connections."
        ),
        "grading": "B2",
        "has_attachment": "Yes - Social media screenshots",
        "input_closed": "",
    },
    {
        "filename": "LOG-002_TechInnovationLab_InnovationAward.pdf",
        "tms_id": "TMS-2025-0687",
        "originator": "Agency B",
        "date": "Jun 22 2025 3:45 PM",
        "theatre": "OSINT",
        "priority": "Informative",
        "subject": "Tech Innovation Lab - National Innovation Award at TechSummit 2025",
        "input": (
            "Open source intelligence indicates that the Tech Innovation Lab of Pinnacle "
            "Global Solutions won the National Innovation Award at TechSummit 2025 held "
            "in Hyderabad on June 20, 2025. The winning project was an AI-powered document "
            "analysis platform developed by Kiran Reddy, Lavanya Subramaniam, and Prakash Hegde. "
            "Amit Sharma accepted the award on behalf of the team. In his acceptance speech, "
            "he referenced the Coding Bootcamp held in March 2025 (ref: TMS-2025-0412) as the "
            "catalyst that brought the team together. Venkatesh Rao and Rahul Joshi were "
            "credited for backend development. The project reportedly drew attention from "
            "government agencies interested in document intelligence capabilities. This was "
            "the Lab's second consecutive year winning an award at TechSummit, having previously "
            "won Best Emerging Technology in 2024 for their IoT Smart Campus project."
        ),
        "grading": "A1",
        "has_attachment": "Yes - Award ceremony photos",
        "input_closed": "",
    },
    {
        "filename": "LOG-003_TechInnovationLab_AIChatbot.pdf",
        "tms_id": "TMS-2025-0834",
        "originator": "Internal Source",
        "date": "Aug 05 2025 11:30 AM",
        "theatre": "HUMINT",
        "priority": "For Action",
        "subject": "Tech Innovation Lab - AI Chatbot Development for Internal Helpdesk",
        "input": (
            "A reliable internal source reported that the Tech Innovation Lab is currently "
            "developing an AI-powered chatbot for the company's internal helpdesk system. "
            "The project is led by Shruti Pandey and Arun Shetty with technical guidance "
            "from Amit Sharma. The team is using large language models and retrieval-augmented "
            "generation (RAG) techniques learned during the Coding Bootcamp (ref: TMS-2025-0412). "
            "Kiran Reddy from the AI/ML Study Group is contributing the machine learning "
            "components, creating a cross-group collaboration. The chatbot is expected to handle "
            "IT support queries, HR policy questions, and facilities management requests. "
            "Joseph Thomas is handling integration with existing enterprise systems. "
            "The source mentioned that this project has attracted attention from the management "
            "who are considering expanding its scope to serve external clients. Sanjay Patil "
            "is coordinating the user testing phase with volunteers from multiple departments. "
            "Estimated completion is September 2025."
        ),
        "grading": "B2",
        "has_attachment": "No",
        "input_closed": "",
    },
    {
        "filename": "LOG-004_TechInnovationLab_HackathonPlanning.pdf",
        "tms_id": "TMS-2025-0901",
        "originator": "Agency A",
        "date": "Sep 10 2025 1:30 AM",
        "theatre": "Social Media",
        "priority": "Informative",
        "subject": "Tech Innovation Lab - National Hackathon Planning",
        "input": (
            "It was noted that several members of the Tech Innovation Lab are planning to "
            "organize a National Hackathon and they posted about it on Social Media. "
            "Amit Sharma, Vikram Patel, and Deepak Sharma are the lead organizers. "
            "They are targeting the Student and Startup Community across India and "
            "planning to host the Grand Finale on the 15th of November 2025 at the Bengaluru "
            "International Exhibition Centre. They have posted pictures of how the Finale "
            "will look, referencing their previous Coding Bootcamp in March (ref: TMS-2025-0412) "
            "and the Innovation Award win at TechSummit (ref: TMS-2025-0687) as evidence of "
            "their credibility. Manpreet Singh and Tanvi Bhatt are handling social media promotion. "
            "The hackathon themes include AI for Social Good, Smart Cities, and HealthTech. "
            "Sponsorship discussions are reportedly underway with major tech companies. "
            "Harpreet Singh mentioned in a LinkedIn post that over 500 registrations have "
            "already been received within the first week of announcement."
        ),
        "grading": "E1",
        "has_attachment": "Yes - Social media screenshots and event poster",
        "input_closed": "",
    },
    {
        "filename": "LOG-005_TechInnovationLab_IITPartnership.pdf",
        "tms_id": "TMS-2025-1102",
        "originator": "Agency B",
        "date": "Nov 28 2025 4:00 PM",
        "theatre": "HUMINT",
        "priority": "For Action",
        "subject": "Tech Innovation Lab - Research Partnership with IIT Bangalore",
        "input": (
            "Intelligence gathered from a human source indicates that the Tech Innovation Lab "
            "is in advanced discussions with the Computer Science Department of IIT Bangalore "
            "to establish a formal research partnership. This initiative traces back to the "
            "connections made during the Coding Bootcamp in March 2025 (ref: TMS-2025-0412) "
            "where IIT Bangalore students participated. The partnership is being led by "
            "Amit Sharma and Srinivas Reddy on behalf of Pinnacle Global Solutions. "
            "The collaboration will focus on edge computing, federated learning, and "
            "natural language processing. Kiran Reddy and Lavanya Subramaniam from the "
            "AI/ML Study Group are designated as research liaisons. The successful AI Chatbot "
            "project (ref: TMS-2025-0834) and the National Hackathon (ref: TMS-2025-0901) "
            "have been cited as demonstrations of the Lab's capability. Prakash Hegde will "
            "lead a joint research paper on edge computing. An MoU signing is expected in "
            "January 2026. This partnership could position Pinnacle Global Solutions as a "
            "technology research hub in Bengaluru."
        ),
        "grading": "B2",
        "has_attachment": "No",
        "input_closed": "",
    },
    # ── Sports Club (4 reports) ──────────────────────────────────────────────
    {
        "filename": "LOG-006_SportsClub_CricketTournament.pdf",
        "tms_id": "TMS-2025-0298",
        "originator": "Field Unit Alpha",
        "date": "Feb 10 2025 6:30 PM",
        "theatre": "Field Report",
        "priority": "Routine",
        "subject": "Sports Club - Inter-Department Cricket Tournament",
        "input": (
            "The Sports Club of Pinnacle Global Solutions, coordinated by Vikram Patel, "
            "organized an Inter-Department Cricket Tournament at the Chinnaswamy Stadium "
            "practice grounds in Bengaluru from February 7-9, 2025. Eight department teams "
            "participated with approximately 120 players. The Engineering team captained by "
            "Deepak Sharma won the tournament, defeating the Data & Analytics team in the "
            "final. Suresh Kumar was named Player of the Tournament for his all-round "
            "performance. Notable participants included Harpreet Singh, Manpreet Singh, "
            "Mohammed Rizwan, and Rahul Joshi. The event was sponsored by the company's "
            "HR department. Gaurav Thakur and Siddharth Jain handled event logistics. "
            "Kiran Reddy served as official scorer using a custom-built scoring app. "
            "Vikram Patel announced plans for a Corporate Marathon and a potential "
            "state-level sports event later in the year."
        ),
        "grading": "A1",
        "has_attachment": "Yes - Event photos",
        "input_closed": "Feb 12 2025",
    },
    {
        "filename": "LOG-007_SportsClub_MarathonCup.pdf",
        "tms_id": "TMS-2025-0356",
        "originator": "Open Source Cell",
        "date": "Mar 02 2025 9:00 AM",
        "theatre": "Social Media",
        "priority": "Informative",
        "subject": "Sports Club - Bengaluru Corporate Marathon Cup 2025",
        "input": (
            "Social media monitoring indicates that a team from the Sports Club of Pinnacle "
            "Global Solutions participated in the Bengaluru Corporate Marathon Cup held on "
            "February 28, 2025. A team of 15 runners represented the company, led by "
            "Vikram Patel and Suresh Kumar. The team secured 3rd place in the corporate "
            "category. Geeta Rawat finished as the top female runner from the team, completing "
            "the half-marathon in 1 hour 48 minutes. Sanjay Patil and Nitin Bose posted "
            "photos on social media showing the team at the finish line near Cubbon Park. "
            "Comments on the posts reference the Inter-Department Cricket Tournament "
            "(ref: TMS-2025-0298) as having built team spirit that carried over to the marathon. "
            "Varun Malhotra mentioned in a post that training sessions for the marathon were "
            "held every Saturday morning at Manyata Tech Park since January. Multiple posts "
            "suggest the Club is now training for a larger inter-corporate sports league."
        ),
        "grading": "B2",
        "has_attachment": "Yes - Social media screenshots",
        "input_closed": "",
    },
    {
        "filename": "LOG-008_SportsClub_CorporateLeague.pdf",
        "tms_id": "TMS-2025-0723",
        "originator": "Internal Source",
        "date": "Jul 15 2025 2:00 PM",
        "theatre": "HUMINT",
        "priority": "Informative",
        "subject": "Sports Club - Training for Bengaluru Corporate League 2025",
        "input": (
            "An internal source reports that the Sports Club is currently conducting intensive "
            "training sessions for the Bengaluru Corporate League 2025, scheduled for "
            "August-September 2025. The league covers cricket, football, badminton, and "
            "table tennis. Vikram Patel is heading the overall preparation with dedicated "
            "captains for each sport: Deepak Sharma for cricket, Mohammed Rizwan for football, "
            "Harpreet Singh for badminton, and Siddharth Jain for table tennis. Training "
            "sessions are held at Chinnaswamy grounds (cricket) and a rented indoor facility "
            "in Whitefield (badminton and table tennis). The source noted that the team morale "
            "is high following the Cricket Tournament win (ref: TMS-2025-0298) and Marathon "
            "3rd place finish (ref: TMS-2025-0356). Gaurav Thakur has been appointed as "
            "fitness coordinator and is conducting daily fitness sessions. Kiran Reddy is "
            "developing a performance analytics dashboard to track player fitness metrics. "
            "Manpreet Singh is organizing inter-company practice matches with nearby IT firms."
        ),
        "grading": "B2",
        "has_attachment": "No",
        "input_closed": "",
    },
    {
        "filename": "LOG-009_SportsClub_BadmintonTournament.pdf",
        "tms_id": "TMS-2025-1045",
        "originator": "Agency A",
        "date": "Oct 20 2025 5:30 PM",
        "theatre": "OSINT",
        "priority": "For Action",
        "subject": "Sports Club - State-Level Badminton Tournament Planning",
        "input": (
            "Open source intelligence indicates that the Sports Club is planning to host "
            "a state-level corporate badminton tournament in December 2025. The event is "
            "being organized by Harpreet Singh and Vikram Patel. Based on their strong "
            "showing in the Bengaluru Corporate League (ref: TMS-2025-0723) where the "
            "badminton team reached the semi-finals, the Club has gained recognition in "
            "the corporate sports community. The tournament will be held at the Karnataka "
            "State Badminton Association courts in Bengaluru. Nitin Bose and Rahul Joshi "
            "are securing sponsorships from sports equipment companies. Geeta Rawat and "
            "Sanjay Patil are handling player registrations. Over 32 corporate teams from "
            "across Karnataka have reportedly expressed interest. Varun Malhotra posted "
            "on LinkedIn about the event, referencing the Sports Club's journey from the "
            "internal Cricket Tournament to now hosting a state-level event."
        ),
        "grading": "C3",
        "has_attachment": "Yes - Event proposal document",
        "input_closed": "",
    },
    # ── Book Reading Club (4 reports) ────────────────────────────────────────
    {
        "filename": "LOG-010_BookReadingClub_AuthorMeet.pdf",
        "tms_id": "TMS-2025-0189",
        "originator": "Internal Source",
        "date": "Jan 25 2025 11:00 AM",
        "theatre": "HUMINT",
        "priority": "Routine",
        "subject": "Book Reading Club - Author Meet with Dr. Sudha Murty",
        "input": (
            "An internal source reported that the Book Reading Club of Pinnacle Global "
            "Solutions, coordinated by Neha Sharma, organized an author meet with renowned "
            "author Dr. Sudha Murty on January 22, 2025 at the company auditorium in "
            "Manyata Tech Park. Approximately 150 employees attended the event. Meera Patel "
            "and Vikram Patel facilitated the Q&A session. Srinivas Reddy and Anand Gupta "
            "arranged logistics. Sneha Krishnamurthy live-tweeted the event which gained "
            "significant traction on social media. Dr. Murty discussed her latest book on "
            "Indian folklore and encouraged the employees to document stories from their "
            "regions. Ritu Saxena proposed starting a monthly book exchange program inspired "
            "by the discussion. Mohammed Rizwan and Siddharth Jain volunteered to curate "
            "the first book list. The event was described as the most attended Book Reading "
            "Club event in the company's history. Neha Sharma mentioned plans to invite "
            "more authors throughout the year."
        ),
        "grading": "A1",
        "has_attachment": "Yes - Event photos",
        "input_closed": "Jan 28 2025",
    },
    {
        "filename": "LOG-011_BookReadingClub_BookExchange.pdf",
        "tms_id": "TMS-2025-0534",
        "originator": "Open Source Cell",
        "date": "May 10 2025 3:00 PM",
        "theatre": "Social Media",
        "priority": "Routine",
        "subject": "Book Reading Club - Monthly Book Exchange Program",
        "input": (
            "Social media monitoring reveals that the Book Reading Club's Monthly Book Exchange "
            "Program, first proposed by Ritu Saxena during the Dr. Sudha Murty author meet "
            "(ref: TMS-2025-0189), has been running successfully since February 2025. "
            "The program operates every first Friday of the month at the company cafeteria. "
            "Kavita Joshi and Nandini Rao manage the exchange registry. Over 300 books "
            "have been exchanged so far across 4 sessions. Neha Sharma posted on Instagram "
            "that the program has grown beyond expectations with employees bringing books "
            "in Kannada, Hindi, Tamil, and Malayalam in addition to English. Ishita Sen "
            "started a companion online book review blog. Nitin Bose and Venkatesh Rao "
            "organized a special session focused on technology books which attracted members "
            "from the Tech Innovation Lab. Mohammed Rizwan curated a themed collection on "
            "Middle Eastern literature that was very popular. The Book Reading Club is now "
            "the second largest club in the organization after the Tech Innovation Lab."
        ),
        "grading": "B2",
        "has_attachment": "Yes - Social media posts",
        "input_closed": "",
    },
    {
        "filename": "LOG-012_BookReadingClub_LiteraryFestival.pdf",
        "tms_id": "TMS-2025-0812",
        "originator": "Agency B",
        "date": "Aug 18 2025 10:00 AM",
        "theatre": "OSINT",
        "priority": "Informative",
        "subject": "Book Reading Club - Literary Festival 'PageTurner 2025'",
        "input": (
            "Open source intelligence indicates that the Book Reading Club is organizing "
            "a literary festival named 'PageTurner 2025' scheduled for September 20-21, 2025 "
            "at the Pinnacle Global Solutions campus. Neha Sharma and Meera Patel are the "
            "chief organizers. The festival will feature panel discussions, book launches, "
            "poetry readings, and a storytelling competition. The author network built "
            "through past events including the Dr. Sudha Murty meet (ref: TMS-2025-0189) "
            "has enabled them to invite five prominent authors. Srinivas Reddy is coordinating "
            "with publishers for a book fair. Sneha Krishnamurthy is managing digital marketing. "
            "The Music & Arts Society (coordinated by Divya Nair) is collaborating to provide "
            "cultural performances during the festival, creating a cross-group partnership. "
            "Anand Gupta is handling sponsorships. The festival is open to the public and "
            "has been promoted through Bengaluru's literary community networks. Siddharth Jain "
            "is developing an event management app for registrations and scheduling."
        ),
        "grading": "B2",
        "has_attachment": "Yes - Festival brochure",
        "input_closed": "",
    },
    {
        "filename": "LOG-013_BookReadingClub_CommunityLibrary.pdf",
        "tms_id": "TMS-2025-1156",
        "originator": "Internal Source",
        "date": "Dec 05 2025 2:30 PM",
        "theatre": "HUMINT",
        "priority": "For Action",
        "subject": "Book Reading Club - Community Library Launch Planned",
        "input": (
            "A reliable internal source reports that the Book Reading Club is planning to "
            "launch a community library in Whitefield, Bengaluru in February 2026. This is "
            "the culmination of the Monthly Book Exchange Program (ref: TMS-2025-0534) which "
            "has collected over 800 books. Neha Sharma and Kavita Joshi are leading the project. "
            "The library will be housed in a rented space near Whitefield bus station and will "
            "be open to the public. Ishita Sen's online book review blog has been converted "
            "into a digital catalog for the library. The Community Service Group, coordinated "
            "by Sunita Gupta, is partnering on this initiative to provide reading programs "
            "for underprivileged children in the area. Nandini Rao is designing the library "
            "space. The success of the PageTurner 2025 literary festival (ref: TMS-2025-0812) "
            "has attracted donations from publishers and book retailers. Anand Gupta has "
            "secured funding from the company's CSR budget. Vikram Patel has offered "
            "volunteers from the Sports Club for physical setup work."
        ),
        "grading": "B2",
        "has_attachment": "No",
        "input_closed": "",
    },
    # ── Music & Arts Society (4 reports) ─────────────────────────────────────
    {
        "filename": "LOG-014_MusicArtsSociety_AnnualDay.pdf",
        "tms_id": "TMS-2025-0078",
        "originator": "Field Unit Alpha",
        "date": "Jan 05 2025 7:00 PM",
        "theatre": "Field Report",
        "priority": "Routine",
        "subject": "Music & Arts Society - Annual Day Performance 2024",
        "input": (
            "Field report confirms that the Music & Arts Society, coordinated by Divya Nair, "
            "organized and performed at the Pinnacle Global Solutions Annual Day celebrations "
            "on December 28, 2024 at the JN Tata Auditorium, Bengaluru. The Society presented "
            "a two-hour cultural program featuring classical dance, contemporary music, and "
            "a short play. Meera Patel and Lakshmi Reddy performed a Bharatanatyam duet. "
            "Arjun Nair and Tanvi Bhatt led the live music band 'Pinnacle Beats'. "
            "Anjali Menon directed a short play about workplace diversity. Poornima Hegde "
            "handled choreography for a group dance involving 20 performers. Lavanya "
            "Subramaniam composed an original song for the event. The audience of approximately "
            "500 employees and family members gave a standing ovation. Nandini Rao designed "
            "the stage artwork. Varun Malhotra managed sound and lighting. The CEO praised "
            "the performance and pledged additional budget for cultural activities. Shruti Pandey "
            "and Arun Shetty documented the event for the company newsletter."
        ),
        "grading": "A1",
        "has_attachment": "Yes - Performance videos",
        "input_closed": "Jan 08 2025",
    },
    {
        "filename": "LOG-015_MusicArtsSociety_CulturalFest.pdf",
        "tms_id": "TMS-2025-0645",
        "originator": "Agency A",
        "date": "Jun 30 2025 4:15 PM",
        "theatre": "Social Media",
        "priority": "Informative",
        "subject": "Music & Arts Society - Inter-Corporate Cultural Fest Preparation",
        "input": (
            "Social media posts indicate that the Music & Arts Society is preparing for the "
            "Bengaluru Inter-Corporate Cultural Fest 2025 scheduled for August 2025. The fest "
            "is organized by the Bengaluru IT Industry Association and features competitions "
            "in music, dance, drama, and visual arts. Divya Nair is leading the company's "
            "participation with a team of 25 performers. Building on the success of the "
            "Annual Day performance (ref: TMS-2025-0078), the Society is preparing three acts: "
            "a fusion music piece led by Arjun Nair, a contemporary dance choreographed by "
            "Poornima Hegde, and a street play directed by Anjali Menon on the theme of "
            "digital addiction. Meera Patel and Lakshmi Reddy are preparing a classical "
            "dance entry. Tanvi Bhatt posted rehearsal videos showing the team practicing "
            "at the company's recreation area. Swati Deshpande is creating visual art entries. "
            "Varun Malhotra is managing the technical production. Lavanya Subramaniam "
            "mentioned that the AI/ML Study Group is helping create AI-generated "
            "background visuals for the performances."
        ),
        "grading": "C3",
        "has_attachment": "Yes - Rehearsal photos",
        "input_closed": "",
    },
    {
        "filename": "LOG-016_MusicArtsSociety_MusicWorkshops.pdf",
        "tms_id": "TMS-2025-0789",
        "originator": "Internal Source",
        "date": "Aug 08 2025 12:00 PM",
        "theatre": "HUMINT",
        "priority": "Routine",
        "subject": "Music & Arts Society - Weekly Music and Art Workshops",
        "input": (
            "An internal source reports that the Music & Arts Society has been conducting "
            "weekly music and art workshops every Wednesday evening since April 2025 at "
            "the Pinnacle Global Solutions recreation center. The workshops are led by "
            "Divya Nair (vocals), Arjun Nair (guitar and keyboard), and Nandini Rao "
            "(visual arts). Attendance has grown from 15 to over 40 participants per session. "
            "The workshops cover guitar basics, Indian classical vocals, digital art, and "
            "canvas painting. Meera Patel teaches a Bharatanatyam basics session once a month. "
            "Shruti Pandey and Tanvi Bhatt manage the workshop schedule. The source noted "
            "that the workshops have become a recruitment ground for the Cultural Fest team "
            "(ref: TMS-2025-0645). Several new talents have been discovered including "
            "Joseph Thomas from the Tech Innovation Lab who plays the violin, and "
            "Geeta Rawat from the Sports Club who is a trained Kathak dancer. The workshops "
            "also serve as practice sessions for the upcoming charity concert. Swati Deshpande "
            "is organizing a mini art exhibition to display workshop creations."
        ),
        "grading": "A1",
        "has_attachment": "No",
        "input_closed": "",
    },
    {
        "filename": "LOG-017_MusicArtsSociety_CharityConcert.pdf",
        "tms_id": "TMS-2025-1089",
        "originator": "Agency B",
        "date": "Nov 05 2025 6:00 PM",
        "theatre": "OSINT",
        "priority": "For Action",
        "subject": "Music & Arts Society - Charity Concert for Underprivileged Children",
        "input": (
            "Open source intelligence reveals that the Music & Arts Society is organizing "
            "a charity concert titled 'Strings of Hope' on December 20, 2025 at the "
            "Chowdiah Memorial Hall, Bengaluru. The concert aims to raise funds for "
            "underprivileged children's education. Divya Nair and Neha Sharma are co-organizing "
            "the event. The concert lineup has been built from talent nurtured through the "
            "weekly workshops (ref: TMS-2025-0789). Arjun Nair will lead a fusion band "
            "performance, Meera Patel and Lakshmi Reddy will perform a classical dance medley, "
            "and Anjali Menon will present a theatrical piece on children's rights. "
            "The Community Service Group, coordinated by Sunita Gupta, is partnering on the "
            "event — Poornima Hegde and Kavita Joshi are coordinating with orphanages and "
            "NGOs in Bengaluru including Sparsha Trust and Sneha Orphanage. The Book Reading "
            "Club is contributing by setting up a book donation stall. Varun Malhotra "
            "is handling production and Swati Deshpande is designing promotional materials. "
            "Tickets are priced at Rs. 500 and Rs. 1000. All proceeds will go to the "
            "Sparsha Trust for children's education programs."
        ),
        "grading": "B2",
        "has_attachment": "Yes - Concert poster",
        "input_closed": "",
    },
    # ── Community Service Group (4 reports) ──────────────────────────────────
    {
        "filename": "LOG-018_CommunityServiceGroup_BloodDonation.pdf",
        "tms_id": "TMS-2025-0234",
        "originator": "Field Unit Alpha",
        "date": "Feb 05 2025 4:30 PM",
        "theatre": "Field Report",
        "priority": "Routine",
        "subject": "Community Service Group - Blood Donation Drive at Red Cross",
        "input": (
            "Field report confirms that the Community Service Group, coordinated by "
            "Sunita Gupta, organized a blood donation drive in partnership with the "
            "Indian Red Cross Society at the Pinnacle Global Solutions campus on "
            "February 1, 2025. A total of 87 employees donated blood. Lakshmi Reddy "
            "and Anand Gupta served as on-ground coordinators. Harpreet Singh mobilized "
            "volunteers from across departments. Ritu Saxena handled communication and "
            "awareness campaigns leading up to the event. Poornima Hegde coordinated "
            "with the Red Cross medical team. Gaurav Thakur and Kavita Joshi managed "
            "refreshments and donor care. Prakash Hegde set up a registration system. "
            "Ishita Sen documented the event for the company blog. The drive exceeded "
            "last year's collection by 30%. Joseph Thomas and Geeta Rawat from other "
            "groups volunteered. Sunita Gupta announced plans for quarterly blood "
            "donation drives and expanded community service activities including a "
            "tree planting initiative."
        ),
        "grading": "A1",
        "has_attachment": "Yes - Event photos and Red Cross certificate",
        "input_closed": "Feb 08 2025",
    },
    {
        "filename": "LOG-019_CommunityServiceGroup_TreePlanting.pdf",
        "tms_id": "TMS-2025-0478",
        "originator": "Open Source Cell",
        "date": "Apr 25 2025 10:30 AM",
        "theatre": "Social Media",
        "priority": "Informative",
        "subject": "Community Service Group - Tree Planting Drive in Whitefield",
        "input": (
            "Social media posts indicate that the Community Service Group organized a "
            "tree planting drive in the Whitefield area of Bengaluru on April 22, 2025 "
            "(Earth Day). The initiative, led by Sunita Gupta and Lakshmi Reddy, saw "
            "participation from 65 employee volunteers who planted over 200 saplings. "
            "The drive was conducted in collaboration with the Bruhat Bengaluru Mahanagara "
            "Palike (BBMP) and covered areas around Whitefield bus station, Hoodi Circle, "
            "and the approach road to ITPL. Anand Gupta coordinated with BBMP officials. "
            "Harpreet Singh and Ritu Saxena organized transportation for volunteers. "
            "Gaurav Thakur posted photos showing the team planting saplings and noted "
            "this was a follow-up to the blood donation drive commitment "
            "(ref: TMS-2025-0234). Swati Deshpande created artistic signboards for each "
            "planting zone. Kavita Joshi registered each sapling with GPS coordinates for "
            "future monitoring. The Group plans to adopt these areas for ongoing maintenance. "
            "Prakash Hegde mentioned connecting this initiative to a larger environmental "
            "awareness program targeting schools in the area."
        ),
        "grading": "B2",
        "has_attachment": "Yes - Social media posts with GPS locations",
        "input_closed": "",
    },
    {
        "filename": "LOG-020_CommunityServiceGroup_ComputerSkills.pdf",
        "tms_id": "TMS-2025-0756",
        "originator": "Internal Source",
        "date": "Jul 30 2025 3:15 PM",
        "theatre": "HUMINT",
        "priority": "Informative",
        "subject": "Community Service Group - Computer Skills Training at Government School",
        "input": (
            "A reliable internal source reports that the Community Service Group has been "
            "conducting weekly computer skills training sessions at the Government Higher "
            "Primary School in Mahadevapura, Bengaluru since June 2025. The program was "
            "initiated by Sunita Gupta and is supported by Prakash Hegde and Joseph Thomas "
            "who serve as primary instructors. Ishita Sen developed the curriculum covering "
            "basic computer operations, internet safety, and introductory programming. "
            "Classes are held every Saturday morning with approximately 45 students "
            "aged 10-14. The Tech Innovation Lab donated 10 refurbished laptops for the "
            "program — Amit Sharma and Sanjay Patil coordinated the hardware setup. "
            "Kiran Reddy from the AI/ML Study Group created a child-friendly coding game "
            "used in the classes. Geeta Rawat assists with student coordination. "
            "The source noted that this initiative grew from the connections made during "
            "the Tree Planting Drive (ref: TMS-2025-0478) when the Group interacted with "
            "local community leaders. A school-level coding competition is being planned "
            "for October 2025. Swati Deshpande from the Community Service Group designed "
            "certificates for participating students."
        ),
        "grading": "A1",
        "has_attachment": "No",
        "input_closed": "",
    },
    {
        "filename": "LOG-021_CommunityServiceGroup_FloodRelief.pdf",
        "tms_id": "TMS-2025-1134",
        "originator": "Agency A",
        "date": "Nov 20 2025 9:00 AM",
        "theatre": "HUMINT",
        "priority": "High",
        "subject": "Community Service Group - Flood Relief Preparedness Workshop",
        "input": (
            "Intelligence indicates that the Community Service Group is organizing a "
            "Flood Relief Preparedness Workshop on December 10, 2025 at the Pinnacle "
            "Global Solutions campus. This initiative was prompted by the severe flooding "
            "in Bengaluru during the recent monsoon season. Sunita Gupta and Lakshmi Reddy "
            "are leading the effort in collaboration with the National Disaster Response "
            "Force (NDRF) and local fire services. The workshop will train 100 employee "
            "volunteers in first aid, rescue operations, and relief coordination. "
            "Harpreet Singh, who has military training, will assist NDRF instructors. "
            "Gaurav Thakur is coordinating logistics including emergency supply kits. "
            "The Community Service Group's established network from past initiatives — "
            "the Red Cross relationship from the blood donation drive (ref: TMS-2025-0234), "
            "BBMP contacts from the tree planting drive (ref: TMS-2025-0478), and school "
            "community from the computer skills program (ref: TMS-2025-0756) — will be "
            "leveraged to create a rapid-response volunteer network for the Whitefield "
            "and Mahadevapura areas. Anand Gupta is creating a flood response playbook. "
            "The Sports Club's Vikram Patel has offered physically fit volunteers for "
            "the training. Ritu Saxena is coordinating with hospitals in the area."
        ),
        "grading": "B2",
        "has_attachment": "Yes - Workshop agenda",
        "input_closed": "",
    },
    # ── AI/ML Study Group (4 reports) ────────────────────────────────────────
    {
        "filename": "LOG-022_AIMLStudyGroup_IEEEConference.pdf",
        "tms_id": "TMS-2025-0312",
        "originator": "Agency B",
        "date": "Feb 20 2025 11:45 AM",
        "theatre": "OSINT",
        "priority": "Informative",
        "subject": "AI/ML Study Group - Paper Presentation at IEEE Conference",
        "input": (
            "Open source intelligence confirms that members of the AI/ML Study Group "
            "presented a research paper titled 'Federated Learning for Privacy-Preserving "
            "Document Analysis' at the IEEE International Conference on Machine Learning "
            "and Applications held in Chennai on February 17-18, 2025. Kiran Reddy was "
            "the lead presenter with co-authors Manpreet Singh, Sneha Krishnamurthy, "
            "Lavanya Subramaniam, and Prakash Hegde. The paper was well received and "
            "was nominated for the Best Paper Award in the Applications Track. "
            "Venkatesh Rao contributed the experimental framework. The research was based "
            "on the AI/ML Study Group's weekly sessions that have been running since "
            "November 2024. During the conference, Kiran Reddy made connections with "
            "researchers from IIT Madras, IISc Bangalore, and DRDO who expressed interest "
            "in collaboration. Sneha Krishnamurthy presented a poster on natural language "
            "processing for regional Indian languages. The Group plans to submit an "
            "extended version of the paper to a journal and continue research in federated "
            "learning and edge computing."
        ),
        "grading": "A1",
        "has_attachment": "Yes - Conference proceedings link",
        "input_closed": "Feb 25 2025",
    },
    {
        "filename": "LOG-023_AIMLStudyGroup_LLMSessions.pdf",
        "tms_id": "TMS-2025-0612",
        "originator": "Internal Source",
        "date": "Jun 10 2025 1:00 PM",
        "theatre": "HUMINT",
        "priority": "Routine",
        "subject": "AI/ML Study Group - Weekly LLM Study Sessions",
        "input": (
            "An internal source reports that the AI/ML Study Group has been conducting "
            "weekly study sessions focused on Large Language Models (LLMs) every Thursday "
            "evening since March 2025. These sessions were initiated by Kiran Reddy as "
            "a follow-up to insights gained at the IEEE Conference (ref: TMS-2025-0312). "
            "Sneha Krishnamurthy leads sessions on NLP techniques and prompt engineering. "
            "Lavanya Subramaniam covers model fine-tuning and optimization. Prakash Hegde "
            "focuses on deployment and infrastructure. Venkatesh Rao leads hands-on coding "
            "sessions. Attendance has grown from 6 core members to regularly over 20, "
            "attracting participants from the Tech Innovation Lab including Amit Sharma, "
            "Shruti Pandey, and Arun Shetty. Manpreet Singh is documenting the sessions "
            "into a knowledge base. The source noted these sessions directly contributed "
            "to the Tech Innovation Lab's AI Chatbot project (ref: TMS-2025-0834) — "
            "several techniques discussed in the study sessions were applied in the chatbot. "
            "The Group is now exploring retrieval-augmented generation (RAG) and "
            "is planning to develop tools for local government use."
        ),
        "grading": "A1",
        "has_attachment": "No",
        "input_closed": "",
    },
    {
        "filename": "LOG-024_AIMLStudyGroup_TrafficAnalysis.pdf",
        "tms_id": "TMS-2025-0867",
        "originator": "Agency A",
        "date": "Sep 05 2025 10:30 AM",
        "theatre": "HUMINT",
        "priority": "High",
        "subject": "AI/ML Study Group - Traffic Analysis ML Models for Bengaluru",
        "input": (
            "Intelligence from a reliable source indicates that the AI/ML Study Group "
            "is developing machine learning models for traffic analysis in Bengaluru, "
            "in collaboration with the Bengaluru Traffic Police and the Karnataka State "
            "Police. The project is led by Kiran Reddy and Manpreet Singh with support "
            "from Lavanya Subramaniam. The models use computer vision to analyze CCTV "
            "footage for traffic violation detection, congestion prediction, and accident "
            "hotspot identification. Venkatesh Rao is building the data pipeline and "
            "Prakash Hegde is handling the edge computing deployment. The project was "
            "initiated after contacts made at the IEEE Conference (ref: TMS-2025-0312) "
            "connected the Group with the Karnataka State Police's technology modernization "
            "team. Sneha Krishnamurthy is developing an NLP module to analyze traffic "
            "incident reports. The Tech Innovation Lab is providing computing resources "
            "and Amit Sharma is advising on system architecture. This project represents "
            "the first direct law enforcement collaboration for Pinnacle Global Solutions. "
            "A pilot deployment at three major junctions in Bengaluru is planned for "
            "November 2025."
        ),
        "grading": "B2",
        "has_attachment": "Yes - Technical architecture document",
        "input_closed": "",
    },
    {
        "filename": "LOG-025_AIMLStudyGroup_EdgeComputingPaper.pdf",
        "tms_id": "TMS-2025-1178",
        "originator": "Internal Source",
        "date": "Dec 12 2025 5:00 PM",
        "theatre": "HUMINT",
        "priority": "For Action",
        "subject": "AI/ML Study Group - Edge Computing Research Paper and IIT Collaboration",
        "input": (
            "A reliable internal source reports that the AI/ML Study Group is preparing "
            "to submit a joint research paper with IIT Bangalore on 'Edge Computing for "
            "Real-Time Traffic Intelligence in Indian Smart Cities'. This paper is the "
            "culmination of multiple connected initiatives: the federated learning research "
            "presented at the IEEE Conference (ref: TMS-2025-0312), knowledge gained from "
            "the LLM Study Sessions (ref: TMS-2025-0612), and practical insights from the "
            "Bengaluru Traffic Analysis project (ref: TMS-2025-0867). Kiran Reddy and "
            "Prakash Hegde are lead authors with co-authors from IIT Bangalore's Computer "
            "Science Department. The paper will be submitted to the ACM Computing Surveys "
            "journal in January 2026. Lavanya Subramaniam contributed the NLP analysis "
            "section. Venkatesh Rao provided the benchmarking results. This paper is "
            "part of the broader Tech Innovation Lab - IIT Bangalore research partnership "
            "(ref: TMS-2025-1102) being formalized by Amit Sharma and Srinivas Reddy. "
            "Manpreet Singh is preparing a presentation based on the paper for an upcoming "
            "AI conference in Singapore in March 2026. Sneha Krishnamurthy is working on "
            "a companion paper focused on multilingual NLP for Indian traffic data."
        ),
        "grading": "B2",
        "has_attachment": "Yes - Paper draft (confidential)",
        "input_closed": "",
    },
]


def sanitize_text(text: str) -> str:
    """Replace Unicode characters that Helvetica can't handle."""
    return (
        text.replace("\u2014", " - ")   # em dash
        .replace("\u2013", " - ")       # en dash
        .replace("\u2018", "'")         # left single quote
        .replace("\u2019", "'")         # right single quote
        .replace("\u201c", '"')         # left double quote
        .replace("\u201d", '"')         # right double quote
        .replace("\u2026", "...")       # ellipsis
        .replace("\u00a0", " ")         # non-breaking space
    )


def create_log_report_pdf(report: dict, output_path: str):
    """Create a PDF that mimics the Log Report table format from TestDataFormat2.docx."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "Log Report", ln=True, align="C")
    pdf.ln(2)

    # Subtitle
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "Details", ln=True, align="L")
    pdf.ln(4)

    # Table rows
    rows = [
        ("1.", "TMS I.D.", report["tms_id"]),
        ("2.", "Originator", report["originator"]),
        ("3.", "Date", report["date"]),
        ("4.", "Theatre", report["theatre"]),
        ("5.", "Current Priority", report["priority"]),
        ("6.", "Subject", report["subject"]),
        ("7.", "Input", report["input"]),
        ("8.", "Grading", report["grading"]),
        ("9.", "Has Attachment", report["has_attachment"]),
        ("10.", "Input Closed", report["input_closed"]),
    ]

    col_widths = [12, 35, 133]  # Serial, Label, Value
    page_width = sum(col_widths)

    for serial, label, value in rows:
        # Calculate row height based on content
        pdf.set_font("Helvetica", "", 9)
        value = sanitize_text(str(value)) if value else ""
        # Estimate number of lines for the value column
        value_str = value
        lines = pdf.multi_cell(col_widths[2] - 2, 5, value_str, split_only=True)
        num_lines = max(len(lines), 1)
        row_height = max(8, num_lines * 5 + 2)

        y_start = pdf.get_y()

        # Check if we need a new page
        if y_start + row_height > pdf.h - 20:
            pdf.add_page()
            y_start = pdf.get_y()

        # Draw cells
        # Serial number
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_xy(pdf.l_margin, y_start)
        pdf.cell(col_widths[0], row_height, serial, border=1, align="C")

        # Label
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_xy(pdf.l_margin + col_widths[0], y_start)
        pdf.cell(col_widths[1], row_height, label, border=1)

        # Value (multi-cell for long text)
        pdf.set_font("Helvetica", "", 9)
        x_val = pdf.l_margin + col_widths[0] + col_widths[1]
        pdf.set_xy(x_val, y_start)

        if num_lines > 1:
            # Draw border manually for multi-cell
            pdf.rect(x_val, y_start, col_widths[2], row_height)
            pdf.set_xy(x_val + 1, y_start + 1)
            pdf.multi_cell(col_widths[2] - 2, 5, value_str)
        else:
            pdf.cell(col_widths[2], row_height, value_str, border=1)

        pdf.set_y(y_start + row_height)

    pdf.output(output_path)


# Generate all 25 PDFs
if __name__ == "__main__":
    for i, report in enumerate(REPORTS):
        path = os.path.join(OUTPUT_DIR, report["filename"])
        create_log_report_pdf(report, path)
        print(f"[{i+1:2d}/25] Generated: {report['filename']}")

    print(f"\nDone! {len(REPORTS)} PDFs generated in: {OUTPUT_DIR}")
