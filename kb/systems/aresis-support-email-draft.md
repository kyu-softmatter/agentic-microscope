# DRAFT — Aresis support: embedded-Python (node API) documentation request

> **Status: draft, not sent.** Written 2026-08-27 as a parallel track to
> [`PyTool-RUN-FIRST.md`](PyTool-RUN-FIRST.md). The two are independent: the
> runbook measures the API from the inside, this asks for the document. Either
> alone is useful; together they cross-check.
>
> **To:** support@aresis.com (User Manual title page)
> **From:** kyuchoi@stanford.edu
>
> When a reply arrives, file it as vendor correspondence following the pattern of
> [`reference/quotes/2026-08-20_teledyne-kinetix22-inquiry_price-and-demo-loan.md`](../../reference/quotes/2026-08-20_teledyne-kinetix22-inquiry_price-and-demo-loan.md)
> — quote figures and wording verbatim, and keep the email itself in the mailbox
> rather than copying it in.

## Before sending — two things to fill in

1. **System serial number.** Read it off System Manager's Connections box. It also
   settles an open question of our own: we inferred `SN >= 130` from the
   Breakpoints mask rendering as four characters, and the serial confirms it
   directly.
2. **Tweez 300 software version.** The installer on that PC is
   `Tweez300Setup_V3.0.2.0.msi`; confirm against the GUI's About dialog, since a
   version-specific answer is much more useful than a general one.

Optionally attach nothing. Every fact cited below is from their own manual or
their own sample scripts, so there is nothing they need from us to answer.

## Draft body

```text
Subject: Tweez 300 — documentation for the GUI's embedded Python (Tw300Nodes node API)

Dear Aresis support,

We run a Tweez 300 system in the Takatori group at Stanford University
(Tweez 300 GUI, software V3.0.2.0, licence Permanent; serial <FILL IN>). We are
automating trap manipulation from Python and have the TCP/IP external control
interface working well — the 28 commands in the User Manual, pp. 66-68.

Our question is about the *other* Python interface: the interpreter embedded in
the GUI. We have been reading the sample tools shipped in the installation's
\Python folder (PyTool_RheoOne.py, PyTool_ForceTime.py, PyTool_General.py) and
have added a read-only survey script of our own alongside them. From those
samples we can see that Tw300Nodes.ReadNode(path) / WriteNode(path, value)
address the GUI's property tree, with paths such as

    Traps.Number
    Traps.Assign Pattern
    Traps.<trap name>.Pattern.Wait States

but we cannot find this interface described in any of the four manuals, and
Manuals\ReadMe.txt does not mention the \Python folder.

The three questions that matter most to us:

1. Is there any documentation for this node interface — a list of valid node
   paths, or the method list of the Tw300Nodes object? Even an internal or
   draft document would help us a great deal.

2. Is there a way to ENUMERATE the tree from Python, i.e. to ask a node for its
   children? That would remove all guesswork about path names on our side.

3. When does the node tree become available? A script invoked from
   ArTw300GUIPythonInit.py at GUI startup gets a non-zero status for every path
   we try, including System.Version — which PyTool_General.py itself reads, so
   we assume the tree is simply not constructed yet at that point. Is there a
   documented hook, event or callback that runs after the GUI model is up? And
   relatedly: how should a PyTool be registered so that it appears in a
   right-click menu, and on which element — a tracking ROI, or the Tools item?
   (We note that the registry file is named ArTw300ROIPythonTools.xml and that
   both sample tools declare DataSource Name="Probe".)

Three further questions, if the interface does reach these:

4. Laser power. The TCP set has LASER_ON / LASER_OFF / BEAM_SET_FOCUS /
   BEAM_SET_PARAMS but nothing for the power level, so at present the power is
   an acquisition parameter we cannot record programmatically. Can it be set or
   read from the embedded Python? And does a saved project restore the power
   level — the manual says a project carries "the state of the laser operation
   and beam setting" (p. 65), but we would rather not discover the answer by
   experiment with a class-4 source.

5. Camera acquire/release. We share one Photometrics Kinetix between the Tweez
   GUI and Micro-Manager, and PVCAM allows only one owner, so the handover is
   currently manual. Is there a software route to release and re-acquire the
   camera?

6. Can the embedded Python be invoked from outside the GUI process — from
   another program, or from the TCP/IP interface?

Finally, two behaviours the manual does not settle, which we would otherwise
have to determine by trial:

7. Repeat > Count — is this the total number of passes, or the number of
   repeats after the first pass?

8. If TRAP_PATT_RELEASE_BP is sent BEFORE the trap reaches the breakpoint, is
   the release remembered (the trap passes through when it arrives) or
   discarded (it must be sent again)?

While reading closely we also noticed three small inconsistencies in the
User Manual (Release November 2021, V20), in case they are useful to you:

  - p. 67 gives LOAD_PATTERN <pattern name> <pattern file>, but the example on
    p. 68 puts the file first. On our system the p. 67 order is the one that
    returns 0.
  - That same example names a pattern file "Sample.tsf", while p. 55 states the
    extension is tpf.
  - p. 69 lists -25 for an element that does not exist, but on our system
    TRAP_DELETE, TRAP_POSITION and TRAP_STRENGTH with an unknown trap name all
    return -22 ("no resource selected"). We had built a readiness check around
    -25 and it reported a healthy GUI as not ready.

Thank you very much — any pointer, even to an undocumented or internal
reference, would save us a lot of time.

Best regards,
Kyu Hwan Choi
Takatori Group, Stanford University
kyuchoi@stanford.edu
```

## Why it is shaped this way

- **Three tiers, explicitly labelled.** Questions 1-3 are the ask; 4-6 are
  conditional on the interface reaching them; 7-8 are cheap. A support engineer
  can answer the first tier and stop, and we still win. A flat list of eight
  questions tends to get one answer or none.
- **Every claim is sourced to their own material** — manual page numbers, their
  sample script filenames, their registry filename. Nothing asks them to trust
  our measurements, so nothing invites a debate about our setup.
- **The errata are last and framed as a courtesy**, not a complaint. They also
  demonstrate we have read the manual properly, which tends to change the quality
  of the reply.
- **Question 4 says why we are asking rather than testing** — a class-4 source is
  a reason support staff recognise, and it makes the question about safety
  practice rather than laziness.
- **What is deliberately not in it:** that we redirected `TW300PYPATH` to a
  writable copy of the \Python folder. It is irrelevant to every question asked,
  the vendor folder is unmodified, and volunteering it mainly invites an
  "unsupported modification" reply. The survey script itself *is* mentioned,
  because question 3 makes no sense without it.
